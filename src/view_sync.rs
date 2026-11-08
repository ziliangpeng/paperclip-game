//! Client-side ordering for complete views from independent HTTP/SSE sources.
//!
//! Stream generations and GET tokens are local bookkeeping. They are not actor
//! credentials, command identities, replay cursors, or server game controls.

use crate::api::GameView;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct StreamToken {
    generation: u64,
    epoch: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct GetToken {
    epoch: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ViewDecision {
    Applied,
    AdoptedNewRun,
    IgnoredLowerRevision,
    EqualPresentationOnly,
    IgnoredStaleSource,
    IgnoredUnexpectedRun,
}

/// Orders typed full views without comparing arrival times across connections.
/// A fresh connection may adopt a new run only through its initial full frame.
#[derive(Debug, Default)]
pub struct ViewSynchronizer {
    current: Option<GameView>,
    epoch: u64,
    next_generation: u64,
    active_stream: Option<StreamToken>,
    presentation_count: u64,
}

impl ViewSynchronizer {
    pub fn current(&self) -> Option<&GameView> {
        self.current.as_ref()
    }

    /// Number of actual baseline/replacement presentations. Equal and ignored
    /// inputs have no presentation effect and cannot cause game effects.
    pub fn presentation_count(&self) -> u64 {
        self.presentation_count
    }

    /// Activate a new local stream generation and invalidate older streams.
    pub fn open_stream(&mut self) -> StreamToken {
        self.next_generation = self
            .next_generation
            .checked_add(1)
            .expect("local stream generation exhausted");
        let token = StreamToken {
            generation: self.next_generation,
            epoch: self.epoch,
        };
        self.active_stream = Some(token);
        token
    }

    /// Bind a GET to the local run epoch in which it was issued. A response for
    /// an already superseded epoch is stale even if its revision is larger.
    pub fn request_view(&self) -> GetToken {
        GetToken { epoch: self.epoch }
    }

    pub fn accept_stream_initial(&mut self, token: StreamToken, view: GameView) -> ViewDecision {
        self.accept_stream(token, view, true)
    }

    pub fn accept_stream_update(&mut self, token: StreamToken, view: GameView) -> ViewDecision {
        self.accept_stream(token, view, false)
    }

    pub fn accept_get(&mut self, token: GetToken, view: GameView) -> ViewDecision {
        if token.epoch != self.epoch {
            return ViewDecision::IgnoredStaleSource;
        }
        self.accept(view, true, None)
    }

    fn accept_stream(&mut self, token: StreamToken, view: GameView, initial: bool) -> ViewDecision {
        if self.active_stream != Some(token) {
            return ViewDecision::IgnoredStaleSource;
        }
        if self
            .current
            .as_ref()
            .is_some_and(|current| current.run_id == view.run_id)
        {
            return self.accept(view, false, Some(token));
        }
        if !initial {
            return ViewDecision::IgnoredUnexpectedRun;
        }
        if token.epoch != self.epoch {
            return ViewDecision::IgnoredStaleSource;
        }
        self.accept(view, true, Some(token))
    }

    fn accept(
        &mut self,
        view: GameView,
        new_run_allowed: bool,
        stream: Option<StreamToken>,
    ) -> ViewDecision {
        if let Some(current) = &self.current
            && current.run_id == view.run_id
        {
            if view.revision < current.revision {
                return ViewDecision::IgnoredLowerRevision;
            }
            if view.revision == current.revision {
                return ViewDecision::EqualPresentationOnly;
            }
            self.current = Some(view);
            self.record_presentation();
            return ViewDecision::Applied;
        }
        if !new_run_allowed {
            return ViewDecision::IgnoredUnexpectedRun;
        }
        self.current = Some(view);
        self.epoch = self
            .epoch
            .checked_add(1)
            .expect("local run epoch exhausted");
        if stream.is_none() {
            self.active_stream = None;
        }
        self.record_presentation();
        ViewDecision::AdoptedNewRun
    }

    fn record_presentation(&mut self) {
        self.presentation_count = self
            .presentation_count
            .checked_add(1)
            .expect("local presentation counter exhausted");
    }
}
