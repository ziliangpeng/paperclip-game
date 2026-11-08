//! Bounded, full-view fan-out from the single authoritative runtime watch.

use crate::api::GameView;
use crate::runtime::{RuntimeHandle, RuntimeView};
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use tokio::sync::{mpsc, watch};

pub(crate) const VIEW_QUEUE_CAPACITY: usize = 8;

#[derive(Clone, Debug)]
pub(crate) struct PublishedView {
    pub(crate) run_id: String,
    pub(crate) revision: u64,
    pub(crate) json: Arc<str>,
}

impl PublishedView {
    fn capture(snapshot: &RuntimeView) -> Result<Self, ViewPublishError> {
        let view = GameView::from_runtime(snapshot).map_err(|_| ViewPublishError)?;
        let json = serde_json::to_string(&view)
            .map(Arc::<str>::from)
            .map_err(|_| ViewPublishError)?;
        Ok(Self {
            run_id: view.run_id,
            revision: view.revision.get(),
            json,
        })
    }

    pub(crate) fn event_id(&self) -> String {
        format!("{}:{}", self.run_id, self.revision)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct ViewPublishError;

pub(crate) struct ViewConnection {
    pub(crate) initial: PublishedView,
    pub(crate) updates: mpsc::Receiver<PublishedView>,
    pub(crate) guard: ConnectionGuard,
}

pub(crate) struct ConnectionGuard(Arc<AtomicUsize>);

impl Drop for ConnectionGuard {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

/// Host-owned shutdown state and the existing runtime handle. No game writer,
/// replay history, or global queue is introduced.
#[derive(Clone)]
pub(crate) struct ViewBroadcast {
    runtime: RuntimeHandle,
    shutdown: Arc<watch::Sender<bool>>,
    active: Arc<AtomicUsize>,
}

impl ViewBroadcast {
    pub(crate) fn new(runtime: RuntimeHandle) -> Self {
        let (shutdown, _) = watch::channel(false);
        Self {
            runtime,
            shutdown: Arc::new(shutdown),
            active: Arc::new(AtomicUsize::new(0)),
        }
    }

    /// Subscription precedes capture. Marking that exact current frame seen
    /// prevents a spurious duplicate while retaining every subsequent change.
    pub(crate) fn connect(&self) -> Result<ViewConnection, ViewPublishError> {
        let mut views = self.runtime.subscribe();
        let initial = PublishedView::capture(&views.borrow_and_update())?;
        let (sender, updates) = mpsc::channel(VIEW_QUEUE_CAPACITY);
        self.active.fetch_add(1, Ordering::AcqRel);
        let guard = ConnectionGuard(Arc::clone(&self.active));
        let shutdown = self.shutdown.subscribe();
        tokio::spawn(publish_updates(
            views,
            initial.run_id.clone(),
            initial.revision,
            sender,
            shutdown,
        ));
        Ok(ViewConnection {
            initial,
            updates,
            guard,
        })
    }

    pub(crate) fn initiate_shutdown(&self) {
        self.shutdown.send_replace(true);
    }

    #[cfg(test)]
    pub(crate) fn active_connections(&self) -> usize {
        self.active.load(Ordering::Acquire)
    }
}

async fn publish_updates(
    mut views: watch::Receiver<RuntimeView>,
    mut last_run_id: String,
    mut last_revision: u64,
    sender: mpsc::Sender<PublishedView>,
    mut shutdown: watch::Receiver<bool>,
) {
    loop {
        if *shutdown.borrow() {
            break;
        }
        tokio::select! {
            biased;
            changed = shutdown.changed() => {
                if changed.is_err() || *shutdown.borrow_and_update() {
                    break;
                }
            }
            changed = views.changed() => {
                if changed.is_err() {
                    break;
                }
            }
        }
        let snapshot = views.borrow_and_update().clone();
        if snapshot.run_id == last_run_id && snapshot.revision <= last_revision {
            continue;
        }
        let Ok(next) = PublishedView::capture(&snapshot) else {
            break;
        };
        match sender.try_send(next) {
            Ok(()) => {
                last_run_id = snapshot.run_id;
                last_revision = snapshot.revision;
            }
            // A lagging or disconnected observer loses only its own transport.
            // Reconnection constructs a new full current baseline.
            Err(mpsc::error::TrySendError::Full(_)) | Err(mpsc::error::TrySendError::Closed(_)) => {
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::amount::Amount;
    use crate::game::rng::GameRng;
    use crate::game::state::GameState;
    use crate::runtime::{Command, CommandId, CommandTestGate, GameRuntime, MonotonicClock};
    use std::future::Future;
    use std::pin::Pin;
    use std::sync::Mutex;
    use std::time::{Duration, Instant};
    use tokio::sync::Notify;
    use tokio::time::timeout;

    struct TestClock {
        now: Mutex<Instant>,
        wake: Notify,
    }

    impl TestClock {
        fn new() -> Self {
            Self {
                now: Mutex::new(Instant::now()),
                wake: Notify::new(),
            }
        }

        fn advance(&self, amount: Duration) {
            let mut now = self.now.lock().unwrap();
            *now = now.checked_add(amount).unwrap();
            drop(now);
            self.wake.notify_one();
        }
    }

    impl MonotonicClock for Arc<TestClock> {
        fn now(&self) -> Instant {
            *self.now.lock().unwrap()
        }

        fn wait_until(&self, _deadline: Instant) -> Pin<Box<dyn Future<Output = ()> + Send + '_>> {
            Box::pin(self.wake.notified())
        }
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn slow_observer_queue_disconnects_while_real_writer_continues() {
        // SSE-DISCONNECT-RECONNECT / RT-NO-CLIENTS-CONTINUOUS: this consumes
        // the product connection directly and deliberately never polls its queue.
        let clock = Arc::new(TestClock::new());
        let gate = Arc::new(CommandTestGate::default());
        gate.release();
        let mut state = GameState::fresh(GameRng::from_test_seed([41_u8; 32]));
        state.pro.wire = Amount::parse("10000").unwrap().nonnegative().unwrap();
        let runtime = GameRuntime::start_with_test_gate(Arc::clone(&clock), state, gate).unwrap();
        let handle = runtime.handle();
        let broadcast = ViewBroadcast::new(handle.clone());
        let ViewConnection {
            initial,
            mut updates,
            guard,
        } = broadcast.connect().unwrap();
        assert_eq!(broadcast.active_connections(), 1);
        assert_eq!(initial.revision, 0);

        let mut expected_updates = 0;
        timeout(Duration::from_secs(5), async {
            while !updates.is_closed() {
                expected_updates += 100;
                clock.advance(Duration::from_secs(1));
                loop {
                    let current = handle.view();
                    if current.game.clock.update_count() >= expected_updates {
                        break;
                    }
                    tokio::task::yield_now().await;
                }
                assert!(updates.len() <= VIEW_QUEUE_CAPACITY);
            }
        })
        .await
        .expect("unpolled product connection reaches its explicit lag disconnect");
        let progressed = handle.view();
        assert!(progressed.game.clock.update_count() >= 100);
        assert!(progressed.revision >= 100);
        assert!(updates.len() <= VIEW_QUEUE_CAPACITY);

        let mut frames = 0;
        let mut previous = initial.revision;
        while let Ok(frame) = updates.try_recv() {
            frames += 1;
            assert!(frames <= VIEW_QUEUE_CAPACITY, "bounded product queue");
            assert!(frame.revision > previous, "latest-coalesced ordering");
            previous = frame.revision;
            let decoded: GameView = serde_json::from_str(&frame.json).unwrap();
            assert_eq!(decoded.revision.get(), frame.revision);
            assert_eq!(decoded.run_id, frame.run_id);
            assert_eq!(decoded.clock.update_count.get(), frame.revision);
        }
        assert!(frames > 0, "some complete updates precede disconnect");
        assert!(frames <= VIEW_QUEUE_CAPACITY);
        assert!(
            previous < handle.view().revision,
            "updates coalesced to later state"
        );

        let receipt = handle
            .execute(Command::make_paperclip(CommandId::new(77).unwrap()))
            .await
            .unwrap();
        assert_eq!(receipt.result, Ok(()));
        assert_eq!(handle.view().game.pro.lifetime_clips.to_string(), "1");
        assert!(handle.view().revision > previous);
        drop(updates);
        drop(guard);
        assert_eq!(broadcast.active_connections(), 0);
        runtime.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn initial_capture_does_not_duplicate_and_drop_shutdown_release_resources() {
        let runtime = GameRuntime::start().unwrap();
        let handle = runtime.handle();
        let broadcast = ViewBroadcast::new(handle.clone());
        let ViewConnection {
            initial,
            mut updates,
            guard,
        } = broadcast.connect().unwrap();
        assert!(matches!(
            updates.try_recv(),
            Err(mpsc::error::TryRecvError::Empty)
        ));
        let current: GameView = serde_json::from_str(&initial.json).unwrap();
        assert_eq!(current.revision.get(), initial.revision);

        broadcast.initiate_shutdown();
        timeout(Duration::from_secs(3), async {
            while !updates.is_closed() {
                tokio::task::yield_now().await;
            }
        })
        .await
        .expect("host shutdown terminates the observer");
        drop(guard);
        assert_eq!(broadcast.active_connections(), 0);
        runtime.shutdown().await.unwrap();

        let broadcast = ViewBroadcast::new(handle);
        let connection = broadcast.connect().unwrap();
        assert_eq!(broadcast.active_connections(), 1);
        drop(connection);
        assert_eq!(broadcast.active_connections(), 0);
    }
}
