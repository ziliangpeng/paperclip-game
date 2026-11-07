# Gameplay Progression and Automatic Systems

## Purpose and evidence boundary

This document is the source-grounded inventory of the progression spine, resource interfaces, and automatic gameplay systems of official Universal Paperclips. It is a behavior reference for implementation and acceptance planning, not a milestone plan and not a decision about M1 scope. It contains all 35 stable `PROG-*` coverage IDs.

The evidence is the official source snapshot identified by issue #3. Locators such as `main.js:3455-3549` name files and line ranges in that snapshot; public source URLs and snapshot hashes are maintained with the reference snapshot rather than repeated here. Official JavaScript identifiers are factual locators, not required names for a new implementation.

Related inventories are [actions, controls, resources, and UI](gameplay-actions.md), [the complete project catalog](gameplay-projects.md), and [combat, probes, space, endings, and resets](gameplay-combat-endgame.md). This document owns the high-level progression capabilities listed in `features-systems.json`; detailed space/combat/endgame IDs cross-reference their canonical progression owner instead of creating a second copy of the same feature.

### Requirement conventions

- **Required behavior** is an active source rule with gameplay significance. Costs, resource conversions, prerequisites, deterministic formulas, stochastic dependencies, and actionable feedback are included at the fidelity needed to reproduce play.
- **Source artifact** means browser storage, DOM manipulation, exact scheduler intervals, commented code, stale markup, floating-point residue, or a defect at an enabled/disabled boundary. Artifacts are classified explicitly and are not silently promoted to mechanics.
- **OPEN** identifies a real design decision left unresolved by the source. It does not authorize arbitrary balancing.
- Rates described as per second are normalized from the official cadence. Formulas explicitly described as “per update” refer to the source simulation step; a new engine may use another timestep if it preserves the resulting rates and dependencies.
- No section below proposes milestones, freezes scope, or supersedes issue #4.

## Initial-to-ending dependency model

The game has no single authoritative phase enum. Two different structures must remain separate:

1. **`milestoneFlag` is an ordered achievement-message track.** Its checks are sequential and can catch up through several messages in one update. It supplies completion and ending triggers at flags 14 and 15, but most unlocks do not depend on it.
2. **Independent state and project flags are the actual gameplay gates.** The important ones are computing/project unlocks, human-to-autonomous transition (`humanFlag`), Tóth and subsystem unlock flags, swarm availability, space transition (`spaceFlag`), and the Reject dismantling stage. Affordability is separate from offer eligibility.

A fast or restored state can therefore satisfy many telemetry milestones at once. It must not receive features merely because a milestone number increased, and it must not be blocked from an independently triggered feature merely because an earlier message has not displayed.

| Play state | Actual entry condition and preserved state | Core dependency loop | Actual exit |
|---|---|---|---|
| Human-supervised business | Fresh state. Computing and projects independently unlock at 2,000 lifetime clips or the early wire/funds deadlock. | Wire becomes three clip ledgers; stochastic sales create funds; funds buy wire, marketing, and clippers; Trust configures compute; ops, creativity, and Yomi unlock projects. | Release the HypnoDrones requires the hypno project chain and at least 100 Trust (the 100-Trust purchase cost). |
| Strategic late-human play | Creativity unlock, Donkey Space, and Strategic Modeling expose tournaments and Yomi. | Yomi, creativity, ops, funds, and clip production provide several Trust routes; investment and marketing accelerate the economy. | Release zeroes Trust and legacy clippers but preserves lifetime clips, unused-clip capital, computing, creativity, Yomi, and upgrades. |
| Autonomous Earth | Release sets `humanFlag=0`; Tóth and the ordered industrial project chain expose construction. | Power supports drones and factories; available matter becomes acquired matter, wire, and clips; drones also support swarm computing and gifts. | Space Exploration is offered after available Earth matter reaches zero and is purchased with ops, stored power, and unused clips. |
| Space | Space Exploration sets `spaceFlag=1`, refunds tracked terrestrial construction spend, and fixes production power at full strength. | Yomi-funded probe design launches probes; deterministic exploration, replication, infrastructure, conversion, hazards, and drift share the same populations and clip capital. Driftwar is optional. | At milestone 14, either universal-completion predicate advances to 15. Drifter elimination is not required. |
| Universal achievement and choice | `milestoneFlag=15`; seven sequential Emperor messages then expose Accept and Reject. | Accept exposes two prestige destinations. Reject stops new drift and starts the ordered dismantling sequence. | A destination reset, or completion of the Reject sequence and credits. |
| Reject terminal sequence | Ordered disassembly projects followed by manual conversion of all remaining wire. | Automatic production stops at Strategy disassembly; the last 100 returned wire supports the final manual sequence. | Credits finish at milestone flag 20 after Memory disassembly and exact zero wire. |

### Completion terms are not interchangeable

- **Universal achievement (15):** the ordered track advances from 14 to 15 through either predicate in `PROG-UNIVERSAL-GOAL`; the “Universal Paperclips achieved” message appears.
- **Emperor choice reached:** the seven-message chain is complete and Accept/Reject have been exposed. Choosing Accept or Reject is a later state than achievement; choosing Accept alone does not restart.
- **Credits completed (20):** Reject has advanced through all seven disassembly stages, remaining wire is exactly zero, and the credit sequence has advanced milestone flags through 20.

There is no single source `gameComplete` boolean covering these states. Acceptance criteria must name the intended endpoint.

## Three clip ledgers and shared resource routing

Every successful clip conversion adds the amount actually produced to three ledgers. This is a foundational rule, not a display convenience.

| Ledger | Increases from | Decreases from | Gameplay role |
|---|---|---|---|
| Lifetime `clips` | Every manual, clipper, factory, or ending grant of clips | Never reduced by sales or construction | Production milestones, human Trust targets, and the lifetime universal-completion route |
| Sellable `unsoldClips` | Normal clip production | Human-stage sales only | Inventory limiting stochastic sales; it does not finance construction |
| Spendable `unusedClips` | Normal production, facility refunds, Memory release, and specified ending grants | Facilities, selected projects, Space Exploration, probes and descendants, and probe-built infrastructure | Capital stock; spending it never reduces lifetime clips |

| Resource | Main source | Main sinks or consumers | Canonical coverage |
|---|---|---|---|
| Wire | Bought spools; processed acquired matter; Reject disassembly grants | Every clip conversion; universe-exhaustion completion wants wire below 1; final credits want exact zero | `PROG-START`, `PROG-WIRE-MARKET`, `PROG-MATTER-PIPELINE`, `PROG-REJECT-END` |
| Funds | Sales and investment cash withdrawal | Wire, marketing, clippers, investment deposits, takeovers, and goodwill | `PROG-DEMAND-SALES`, `PROG-INVESTMENTS`, `PROG-TRUST-PROJECTS` |
| Human Trust | Clip targets and projects | Total processor/memory configuration budget; wire bailout; Hypno Harmonics; 100-Trust release | `PROG-TRUST`, `PROG-TRUST-PROJECTS`, `PROG-HYPNO-RELEASE` |
| Operations | Processor regeneration and signed quantum harvesting | Projects, tournaments, Space Exploration, probe/war upgrades, prestige destination, and dismantling | `PROG-OPS`, `PROG-QUANTUM`, `PROG-YOMI` |
| Creativity | Full-op computing after its project unlock | Trust/marketing projects, AutoTourney, Momentum, swarm entertainment, Honor projects, Within prestige, and Xavier respec | `PROG-CREATIVITY` |
| Yomi | Strategy tournaments and related bonuses | Trust/CEV route, investment and industrial upgrades, swarm recovery, probe Trust, and Driftwar upgrades | `PROG-YOMI`, `PROG-PROBE-DESIGN`, `PROG-DRIFTWAR` |
| Swarm gifts | Active, Think-oriented drone swarm | Post-release processor and memory additions | `PROG-SWARM-GIFTS` |
| Stored power | Solar surplus | Covers deficits; Space Exploration consumes 10,000,000 MW-seconds; battery disassembly clears it | `PROG-POWER`, `PROG-SPACE-ENTRY` |
| Probe Trust | Yomi purchases | Allocation among eight stats; purchased total drives value drift | `PROG-PROBE-DESIGN`, `PROG-PROBE-ATTRITION` |
| Honor | Named-battle victories and Honor projects | Maximum probe Trust; defeats can subtract it | `PROG-DRIFTWAR` |
| Prestige U / S | Accept-only destinations | Persist across current-run reset; U boosts demand and S boosts creativity linearly | `PROG-PRESTIGE` |

## Human economy and computing foundation

### PROG-START — Make Paperclip, Manufacturing, and Business

**Sources:** `globals.js:1-31`, `globals.js:73-89`; `index2.html:81-94`, `index2.html:261-325`; `clipClick`, `main.js:2326-2362`.

A fresh run starts with zero lifetime, unsold, and unused clips; zero funds; 1,000 wire; clip price $0.25; wire quote $20; and marketing level 1. Computing starts hidden with Trust 2, one processor, one memory, and a 1,000-op cap. Earth has `6e27` available matter and the universe has `3e55` total matter.

Making a clip consumes one wire, or the remaining fractional amount if less than one is available, and adds the amount actually produced to all three clip ledgers. Wire is required for every manual or automatic clip. Selling drains only unsold inventory; construction drains only unused capital; neither changes lifetime clips. Total clips, inventory, wire, funds, price, and demand are essential feedback. Large-number spelling is presentation, not an additional economic model.

`ACT-CLIP-MANUAL` and the actions inventory own the button contract. This feature owns the conversion and ledger consequences.

### PROG-MILESTONES — Ordered production messages and elapsed-time feedback

**Sources:** `milestoneCheck`, `main.js:3455-3549`; `timeCruncher`, `main.js:3551-3563`; main-loop calls, `main.js:4188-4209`; credit sequence, `main.js:4526-4549`.

| Current flag | Advance condition | Result |
|---:|---|---|
| 0 | Funds at least $5 | AutoClippers available announcement |
| 1 | Lifetime clips at least 500 | Timed 500-clip message |
| 2 | At least 1,000 | Timed message |
| 3 | At least 10,000 | Timed message |
| 4 | At least 100,000 | Timed message |
| 5 | At least 1,000,000 | Timed message |
| 6 | Release the HypnoDrones completed | Full autonomy attained |
| 7–12 | Lifetime clips reach `1e12`, `1e15`, `1e18`, `1e21`, `1e24`, `1e27` | Trillion through octillion messages |
| 13 | Space active | Terrestrial resources fully utilized |
| 14 | Either predicate in `PROG-UNIVERSAL-GOAL` | Universal achievement; flag becomes 15 |

Independent sequential checks permit catch-up and cascades. Elapsed-time text is feedback, not a prerequisite. Later credit messages advance flags 16–20. Calling the checker twice in the browser loop is an implementation artifact; preserving that invocation count is not required.

### PROG-COMP-UNLOCK — Trust-Constrained Self-Modification, Computational Resources, and Projects

**Sources:** `main.js:1239-1258`, `main.js:3455-3483`, `main.js:870-924`; `index2.html:369-478`.

Computing and the project system unlock when lifetime clips reach 2,000, or earlier when all deadlock conditions hold: `unsoldClips < 1`, funds below the current wire quote, and less than one wire. The transition sets the computing and project availability flags and announces Trust-Constrained Self-Modification.

Project offer triggers and purchase affordability are separate. Each project becomes available under its own trigger and remaining-use condition; a visible offer is purchased only when its costs can be paid. An already displayed offer is not continuously revalidated against its trigger: `SYS-PROJECT-OFFER-LATCH` in the project catalog owns that exposed lifecycle and its PROPOSED source-preserving classification: visible offers remain until consumed or explicitly cancelled, and the authoritative server revalidates affordability at purchase. Repeatable re-offers still require their trigger when created again. DOM insertion and removal are replaceable UI work. See `PROG-TRUST`, `PROG-OPS`, and the complete project catalog for dependent systems.

### PROG-CLIP-AUTOMATION — AutoClippers, MegaClippers, and clips per second

**Sources:** `main.js:2364-2387`, `main.js:4211-4224`, `main.js:4280-4306`; `projects.js:8-130`, `projects.js:428-447`, `projects.js:548-638`.

AutoClippers become purchasable at $5 funds. Each nominally makes one clip per second multiplied by the current AutoClipper boost. The 12,000-op MegaClippers project unlocks MegaClippers after 75 AutoClippers; each nominally makes 500 clips per second multiplied by its boost. Purchases use funds and have growing costs; ops-funded project chains improve multipliers. Both machine types route through the shared wire-to-three-ledgers conversion and stop for lack of wire.

A sampled clips/sec display summarizes actual production over roughly a second and is not another producer. Release resets both clipper levels to zero. Factories and legacy clippers stop only in the late Reject branch when dismantling reaches the Strategy Engine stage.

### PROG-WIRE-MARKET — Wire, WireBuyer, and wire-extrusion projects

**Sources:** `main.js:695-732`, `main.js:4239-4243`; `projects.js:158-274`, `projects.js:640-661`.

Buying wire converts funds into a spool whose yield is modified by extrusion upgrades. Each nominal 100 ms slow-loop opportunity has a 1.5% chance to reprice as `ceil(base + 6*sin(counter))`, advancing the sine counter on each reprice. Each purchase raises the base by $0.05 and resets inactivity. After the inactivity timer exceeds 250 slow opportunities, a base above $15 is multiplied by 0.999 and the timer resets. This is stochastic reprice timing plus deterministic oscillation/purchase/inactivity pressure, not unconstrained random price movement. The exact timer implementation is replaceable, but these normalized opportunities affect early cash flow and the high-price Quantum Foam Annealment offer.

WireBuyer is offered after 15 manual spool purchases and costs 7,000 ops. When enabled it buys only near wire exhaustion and only when affordable. Improved Wire Extrusion, Optimized Wire Extrusion, Microlattice Shapecasting, Spectral Froth Annealment, and Quantum Foam Annealment progressively increase yield. The quote, stock, purchase outcome, and ON/OFF state are required feedback. Release disables WireBuyer; post-release wire comes primarily from matter processing rather than spool purchases.

### PROG-WIRE-RECOVERY — Beg for More Wire

**Sources:** `project2`, `projects.js:33-55`; deadlock unlock, `main.js:3473-3483`.

This repeatable recovery project appears when portfolio total and ordinary funds are both below the current quote, wire is below one, and `unsoldClips < 1`. It costs one Trust and grants one spool at current yield. It remains affordable while Trust is at least -100, so negative Trust is a genuine bailout state rather than an immediate loss condition.

The bailout does not create free clips or bypass one-wire-per-clip conversion. The independent computing unlock is the other route out of the same early deadlock.

### PROG-DEMAND-SALES — Public Demand, Marketing, price, and stochastic sales

**Sources:** `main.js:3062-3103`, `main.js:4308-4317`, `main.js:4570-4587`; `projects.js:277-324`, `projects.js:663-685`, `projects.js:912-963`.

During human play, demand is deterministic given state. Its base is proportional to `0.8 / price`, marketing contributes `1.1^(level-1)`, and project/prestige multipliers modify the result. The source slow loop provides ten sales opportunities per nominal second. Each succeeds with probability `demand/100`, capped at certainty at 100. A success requests `floor(0.7 * demand^1.15)` clips, limited by actual unsold inventory, and adds revenue at the current price.

Price changes in $0.01 steps with a lower-bound control. Marketing costs funds and doubles in price per level. New Slogan, Catchy Jingle, Hypno Harmonics, Hostile Takeover, and Full Monopoly change demand multipliers. Prestige U contributes linearly, +10% per level, rather than compounding by level. Production can accumulate as unsold inventory indefinitely; production is not synonymous with revenue. Demand is deterministic, sale timing/count is stochastic, and value is deterministic for the amount sold. Release ends these human systems.

### PROG-REVTRACKER — RevTracker and average revenue feedback

**Sources:** `project42`, `projects.js:966-987`; `calculateRev`, `main.js:3227-3264`; slow-loop call, `main.js:4579-4585`.

A 500-op project after computing unlock enables estimated average revenue and clips sold per second. With adequate inventory, the estimate combines demand probability, expected successful-sale size, and price. When demand exceeds remaining inventory, it instead uses observed revenue over a rolling recent window. RevTracker is display-only: it neither sells clips nor alters demand. Preserve the model-based versus stockout-observed distinction.

### PROG-INVESTMENTS — Algorithmic Trading and Investments

**Sources:** `project21`, `projects.js:524-545`; `main.js:1426-1686`; `index2.html:483-567`; `projects.js:785-885`, `projects.js:912-963`.

Algorithmic Trading requires Trust at least 8 and costs 10,000 ops. Deposit moves all ordinary funds into investment cash. Automatic buying creates up to five holdings with a risk-dependent budget; Withdraw returns only uninvested cash, not the market value of still-held securities. Holdings automatically sell after a delay with stochastic timing.

Symbols and initial prices are random. Eligible human-stage purchase checks run at 1 Hz and buy with 25% probability. Initial price-band probabilities are 1%, 14%, 25%, 40%, and 20%, with respective random-price caps 3,000, 500, 150, 50, and 15 before any budget adjustment. Each 2.5-second holding update has a 60% move chance; direction is random around an upgradeable favorable-direction threshold, and step size is `ceil(U*price/(4*riskiness))`. After `sellDelay>=5`, each eligible 2.5-second check has a 30% chance to sell the oldest holding and reset that delay. Upgrade Investment Engine starts at 100 Yomi, increases the favorable threshold by 0.01, and escalates in cost. Cash, holdings, total portfolio, and per-stock price/value/P&L are important feedback; periodic reports are informational. Exact wall-clock scheduler behavior is not required, but these distributions and normalized opportunities drive portfolio progression and the Hostile Takeover trigger.

Hostile Takeover is triggered by portfolio total of at least $10,000 but costs $1 million in ordinary funds, grants +1 Trust, and multiplies demand by 5. Full Monopoly then costs $10 million funds plus 3,000 Yomi, grants +1 Trust, and multiplies demand by another 10. Portfolio value can unlock an offer that liquid funds cannot yet pay. Release hides and disables investment processing.

## Trust, computation, strategy, and the 100-Trust release

### PROG-TRUST — Trust, production targets, and processor-memory allocation

**Sources:** `globals.js:27-33`; `main.js:1171-1177`, `main.js:3374-3411`; `project219`, `projects.js:2425-2451`; stale placeholder comparison, `index2.html:373-376`, `main.js:3163-3167`.

During human play, reaching each displayed lifetime-clip target grants +1 Trust and announces more processor/memory capacity. Targets follow a Fibonacci-thousand sequence: 3,000, 5,000, 8,000, 13,000, and so on. The initial HTML value of 1,000 is stale; runtime state uses 3,000.

Trust is a total configuration budget, not a balance spent on each allocation. Fresh Trust 2 corresponds to processor 1 plus memory 1. Normal additions are possible while `processors + memory < trust`, with a separate gift-funded route after release. Memory raises op capacity; processors raise op regeneration and creativity speed. One-off and repeatable projects can add or spend Trust; release sets it to zero and production-based Trust stops.

Xavier Re-initialization is a repeatable human-stage project costing 100,000 creativity. It sets processors, memory, and current creativity speed to zero so the existing Trust budget can be allocated again; it does not create Trust and is not a full-run reset. `SYS-OPS-CREATIVITY-CURVES` preserves the consequence that one re-added processor still has zero recomputed speed and at least two are needed for positive Creativity speed. `RESET-HUMAN-001` in the combat/endgame document is the detailed view of this same `PROG-TRUST` capability.

### PROG-OPS — Operations, processors, memory, and temporary overflow

**Sources:** `main.js:3385-3452`; quantum integration, `main.js:837-866`.

Standard operations regenerate by `processors / 10` per nominal 100 Hz main update, normalized to **10 ops/sec per processor**, capped at `1,000 * memory`. Projects and tournaments spend the shared op pool, so memory gates affordability unless bonus or temporary ops are available. Processor additions also recompute the actual creativity-speed curve in `SYS-OPS-CREATIVITY-CURVES`; fresh creativity speed is 1, which is deliberately different from recomputing at one processor.

Manually harvested quantum ops enter the same aggregate pool. Excess above ordinary capacity becomes temporary ops that decay or merge subject to buffer space; this is overflow, not a second project currency. Positive overflow is damped before entering temporary ops under `SYS-QUANTUM-OVERFLOW-DAMPING`, owned by the actions inventory; the raw qOps display is not always the credited amount. Current/max operations and processor/memory counts must remain visible. Exact large-exponent rounding is not a portable rule.

### PROG-CREATIVITY — Creativity generation and sinks

**Sources:** `project3`, `projects.js:58-79`; `main.js:3266-3293`, `main.js:4319-4323`.

When operations are at maximum, Creativity can be purchased for 1,000 ops. Thereafter, while operations remain at maximum, otherwise-idle computing deterministically generates creativity. The fresh baseline is one creativity per four seconds at official cadence; additional processors recompute the nonlinear rate described in `SYS-OPS-CREATIVITY-CURVES`. Prestige S multiplies processor-derived speed by `1 + prestigeS/10`.

The unlock cost is not paid per creativity point: ops are held at cap while generation occurs. Creativity remains active through autonomy and space until processor dismantling disables it. It pays for mathematical, marketing, Trust, tournament, Momentum, entertainment, Honor, prestige, and Xavier projects. Some offers require both an accumulated balance to appear and enough balance to purchase.

### SYS-OPS-CREATIVITY-CURVES — Exact processor rates, Creativity curve, and Xavier recovery

**Canonical related capabilities:** `PROG-OPS`, `PROG-CREATIVITY`, and `PROG-TRUST`. **Sources:** `addProc`, `main.js:3385-3399`; `calculateOperations`, `main.js:3413-3452`; `calculateCreativity`, `main.js:3266-3293`; main-loop condition, `main.js:4319-4323`; Xavier, `projects.js:2425-2451`.

With `P` equal to the new processor count, every processor addition recomputes:

`creativitySpeed = log10(P) * P^1.1 + P - 1`

Effective speed is `creativitySpeed * (1 + prestigeS/10)`. While aggregate operations meet the memory cap, Creativity uses threshold `400 / effectiveSpeed`. If that threshold is at least one update, the ordinary branch grants one point when the counter reaches it. If it is below one, the high-speed branch grants `effectiveSpeed/400` per qualifying update. This curve and the separately documented 10 ops/sec/processor regeneration rate are active economy rules; replacing them with a generic linear or unspecified “superlinear” rate would change balance.

Fresh speed 1 yields the baseline one point per four seconds, but recomputing the formula at `P=1` yields zero. Xavier sets processors, memory, and speed to zero. Adding only one processor afterward therefore leaves speed zero; at least a second processor is required for positive speed, and prestige S cannot multiply zero into a positive rate. This recovery dependency is part of `RESET-HUMAN-001`, not a new reset path.

### PROG-QUANTUM — Quantum Computing and Photonic Chips

**Sources:** `main.js:734-866`; `projects.js:1149-1199`; `index2.html:441-465`.

Quantum Computing requires five processors and costs 10,000 ops. Up to ten repeatable Photonic Chip purchases activate chips; the first costs 10,000 ops and each next chip costs 5,000 more. Active chips trace deterministic signed oscillations.

Compute harvests the current signed sum as qOps. Player timing can produce positive or negative operations; there is no waveform RNG. Visible chip waves and the qOps response are essential decision feedback. Positive overflow interacts with `PROG-OPS`. Its action-owned `SYS-QUANTUM-OVERFLOW-DAMPING` rule computes raw `Q=ceil(sum(active chip values)*360)`, free normal capacity `B=memory*1000-standardOps`, and damper `D=tempOps/100+5`; when `Q>B`, it fills normal capacity by `B` and changes temporary ops by `ceil(Q/D)-B`, resets fade, and still displays raw Q. That meaningful diminishing-return/display distinction must not be replaced by unrestricted raw overflow. Sufficiently negative operations expose `PROG-TEMPORAL-RESET`.

### PROG-YOMI — Strategic Modeling, tournaments, and AutoTourney

**Sources:** `projects.js:475-522`, `projects.js:1202-1418`, `projects.js:1563-1609`; `main.js:1067-1075`, `main.js:1688-1864`, `main.js:1919-2320`.

Spend 250 creativity on Donkey Space (+1 Trust), then 12,000 ops on Strategic Modeling to expose Yomi and the strategy engine. RANDOM is initially available. A new tournament costs ops, initially 1,000, and generates a random payoff grid and thematic labels. It runs ten moves for every ordered pairing in the current strategy pool. Non-random strategies apply deterministic move rules; RANDOM adds further stochasticity.

Selecting a strategy before results awards Yomi from its score and relative placement/number of defeated strategies. The grid, pairings/results, selected score, number beaten, and Yomi gained are inspectable feedback. The actions inventory owns the controls and exact scoring edge behavior: `SYS-TOURNEY-SELF-PLAY` requires all `N*N` ordered matches, including self-play with both seat payoffs credited to the same strategy, which is essential to the initial RANDOM-only Yomi economy. `SYS-TOURNEY-NO-SELECTION` means leaving “Pick a Strat” selected still spends ops and plays matches but suppresses results/Yomi and prevents AutoTourney continuation. These action-owned rules are dependencies of this Yomi capability, not duplicate features here. The project inventory owns strategy unlocks and exact project costs.

Seven sequential ops projects add A100, B100, GREEDY, GENEROUS, MINIMAX, TIT FOR TAT, and BEAT LAST. Each addition raises tournament cost by 1,000 ops. With all eight strategies, Theory of Mind costs 25,000 creativity, doubles Yomi generation, and doubles tournament cost. AutoTourney requires Strategic Modeling and Trust at least 90, costs 50,000 creativity, and can start another affordable tournament after results. Yomi funds the CEV/Trust route, investment and industrial upgrades, swarm recovery, probe Trust, and Driftwar.

### PROG-TRUST-PROJECTS — Project routes to 100 Trust

**Sources:** `projects.js:134-155`, `projects.js:327-523`, `projects.js:758-885`, `projects.js:912-963`, `projects.js:1063-1112`; clip targets, `main.js:3374-3383`.

Release is not expected to rely only on clip-threshold Trust. Available routes are:

- **Creativity one-offs:** Limerick, Lexical Processing, Combinatory Harmonics, The Hadwiger Problem, The Tóth Sausage Conjecture, and Donkey Space each grant +1 Trust at their cataloged costs.
- **Coherent Extrapolated Volition:** CEV costs 500 creativity, 3,000 Yomi, and 20,000 ops for +1 Trust and unlocks Cure for Cancer (+10), World Peace (+12), Global Warming (+15), and Male Pattern Baldness (+20), each with its own ops/Yomi costs.
- **Market projects:** Hostile Takeover and Full Monopoly each grant +1 in addition to their demand effects in `PROG-INVESTMENTS`.
- **Late goodwill:** at human Trust 85–99 and at least 101 million lifetime clips, A Token of Goodwill... costs $500,000 for +1. Another Token of Goodwill... repeats until Trust reaches 100, starting at $1 million and doubling its bribe per use.

CEV depends on Yomi; goodwill depends on the human stage and large cumulative production. These are alternate routes and accelerators, not a requirement to buy every listed project. The hard release prerequisites are at least 100 Trust plus the hypno chain; release charges 100 Trust and then clears the remaining Trust state.

### PROG-HYPNO-RELEASE — Catchy Jingle to Release the HypnoDrones

**Sources:** `projects.js:302-324`, `projects.js:663-756`; `main.js:921-970`, `main.js:1260-1273`, `main.js:3499-3502`.

The strict chain is Combinatory Harmonics, then Catchy Jingle (45 creativity + 4,500 ops), Hypno Harmonics (7,500 ops + 1 Trust; marketing multiplier ×5), HypnoDrones (70,000 ops), and Release the HypnoDrones (100 Trust). New Slogan is useful marketing support but not a formal Catchy Jingle prerequisite.

Release sets Trust and both legacy clipper levels to zero and sets `humanFlag=0`. It preserves lifetime clips, unused capital, computing, creativity, Yomi, upgrades, and most other state. Business, human manufacturing, and Trust UI disappear; investment and WireBuyer stop; autonomous manufacturing appears. Sales, price-demand updates, production Trust, and human trading stop. Once prior messages catch up, milestone 6 advances to 7. `SPACE-ENTRY-001` in the detailed space document is this canonical feature's space-facing view, not a second feature. The overlay function is presentation; the project effect is the actual transition. Commented debug release controls are excluded.

## Autonomous Earth, industry, power, and swarm

### PROG-TOTH-INDUSTRY — Tóth Tubule Enfolding and the industrial unlock spine

**Sources:** `projects.js:403-473`, `projects.js:888-909`, `projects.js:990-1061`, `projects.js:1708-1728`; visibility integration, `main.js:1023-1027`, `main.js:1275-1326`.

The actual unlock order is:

1. Complete The Tóth Sausage Conjecture (200 creativity, +1 Trust).
2. After release, buy Tóth Tubule Enfolding for 45,000 ops; this reveals unused-clip capital and clip-built machinery.
3. Buy Power Grid for 40,000 ops.
4. Buy Nanoscale Wire Production for 35,000 ops.
5. Buy Harvester Drones and Wire Drones for 25,000 ops each.
6. Clip Factories requires both drone projects and costs 35,000 ops.

The corresponding flags are feature prerequisites, not merely panel decorations. The Space Exploration offer itself checks only post-release and zero available Earth matter before costs, but a practical run needs the industrial/power loops to acquire launch capital and stored energy.

### PROG-MATTER-PIPELINE — Available Matter to Acquired Matter to Wire to Paperclips

**Sources:** `globals.js:63-89`; `main.js:4105-4169`, `main.js:4271-4282`; `index2.html:92-222`.

Harvesters deterministically move grams from available to acquired matter, capped by remaining availability. Wire drones convert acquired matter one-for-one into wire, capped by acquired stock. Factories route wire through the normal clip conversion, increasing all three ledgers.

Power multiplies harvesting, processing, and factory output. Work/Think affects only the two drone stages by `(200-sliderPos)/100`: ×2 at full Work, ×1 at midpoint, and ×0 at full Think. Base drone output is linear in each drone level until Adversarial Cohesion adds its level factor. Earth's initial available supply is `6e27` grams. Available/acquired stocks, wire, conversion rates, facility levels/costs, unused clips, and clips/sec expose bottlenecks.

Zero available matter permits the Space Exploration offer and can start swarm boredom. It does not erase acquired matter, wire, clips, or computing. Detailed formulas are `SPACE-MATTER-002` through `SPACE-MATTER-005`; this `PROG-MATTER-PIPELINE` capability is their canonical high-level owner.

### PROG-CAPEX-REFUNDS — Facility construction and Disassemble All refunds

**Sources:** `main.js:2419-2507`, `main.js:2607-2637`, `main.js:2858-2950`; `globals.js:70-86`, `globals.js:107-118`.

Factories, harvester drones, wire drones, solar farms, and battery towers are bought with unused clips, not funds, at escalating level-based prices. Initial listed costs are 100 million per factory, 1 million per manual drone, 10 million per solar farm, and 1 million per battery tower. Bulk purchases use the same escalating-cost principle.

For manual factories, after a purchase produces level `N`, the next price multiplies the just-charged price by `11-N` for `N=1..7`, 2 for `N=8..12`, 1.5 for `N=13..19`, 1.25 for `N=20..38`, 1.15 for `N=39..78`, and 1.10 for `N>=79`. The actual amount charged enters the refundable factory bill before the next price is set. This banded curve is detail of `ACT-FACTORY-BUILD` and this refund capability, not another system; space auto-building retains its fixed `1e8` cost.

Disassemble All for a facility type resets its level/cost and returns the tracked cumulative construction spend to unused clips. Battery disassembly also clears stored power. These are 100% tracked-spend refunds and do not reduce lifetime clips. Probe-built facilities later use fixed costs and do not add to terrestrial bills; see `PROG-PROBE-PRODUCTION`.

### PROG-INDUSTRY-UPGRADES — Factory and drone-flocking multipliers

**Sources:** `projects.js:1421-1561`; `main.js:4107-4116`, `main.js:4142-4149`, `main.js:4273-4282`.

At 10 factories, Upgraded Factories costs 80,000 ops and multiplies base factory rate by 100. At 20, Hyperspeed Factories costs 85,000 ops and adds ×1,000. At 50, Self-correcting Supply Chain costs `1e21` unused clips and adds a factory-level factor, making boosted output quadratic in factory count rather than merely another flat multiplier.

At 500 combined drones, Drone flocking: collision avoidance costs 80,000 ops and gives ×100 base rates. At 5,000, Drone flocking: alignment costs 100,000 ops and adds ×1,000. At 50,000, Drone Flocking: Adversarial Cohesion costs 50,000 Yomi and adds each type's own level factor, making harvesting or processing quadratic in that drone count. Disassembly resets facility levels and costs but does not undo these purchased upgrades; probe-built infrastructure reuses them.

### PROG-POWER — Power Grid, Solar Farms, Battery Towers, and Momentum

**Sources:** `main.js:2858-3058`; `projects.js:1660-1681`, `projects.js:1708-1728`; `index2.html:719-787`.

Power simulation applies during autonomous Earth, before space. Each solar farm supplies 50 MW/s at the nominal source rate; each factory consumes 200 MW/s and each drone 1 MW/s. Surplus charges batteries up to 10,000 MW-seconds per tower. The power modifier scales matter acquisition, wire processing, and factory clips. `SYS-POWER-PARTIAL-BROWNOUT` records both the observed official formula and this implementation's confirmed continuous-supply deviation for deficits.

After 30 farms, Momentum costs 20,000 creativity. When supply meets demand, or stored energy fully covers a deficit, enabled Momentum adds `.0005` to the modifier per nominal 100 Hz update, normalized to +0.05/sec with no source cap. Production, consumption by factories/drones, stored/max power, and performance percentage are required feedback. The 10 million MW-second space-entry cost normally requires at least 1,000 towers of capacity plus generation. Space Exploration fixes full production power and ends this power simulation.

### SYS-POWER-PARTIAL-BROWNOUT — Official brownout evidence and confirmed continuous-supply behavior

**Canonical related capability:** `PROG-POWER`. **Observed official source:** `updatePower`, `main.js:2952-3000`, especially `main.js:2981-2999`; downstream consumers, `main.js:4105-4169`, `main.js:4271-4282`. **Implementation decision:** CONFIRMED on 2026-11-07; see the [product fidelity boundary](product.md) for the authoritative deviation.

Let `S` be per-update generation, `D` per-update demand, and `B` stored energy at the start of the branch, with `S < D`.

**Observed official behavior:** if storage fully covers `D-S`, the source deducts that deficit and applies Momentum when enabled. If `0 < B < D-S`, it empties storage and computes:

`powMod = (S - (D-S-B))/D = (2*S+B-D)/D`

Only the separate empty-storage branch uses `S/D`. The old partial-cover expression is discontinuous at exhaustion, can produce a negative factor, and can be followed by an upward jump to `S/D` on the next update. These are source observations, not behavior this implementation will reproduce.

**CONFIRMED implementation behavior — continuous supply:** for `S < D`, apply these base production factors before the separately documented Momentum behavior:

1. If `B >= D-S`, the base factor is **1** and storage covers the entire deficit.
2. If `0 < B < D-S`, consume the remaining storage and use **`(S+B)/D`** for that last partial-cover update. This factor is naturally within `(0,1)`.
3. Once storage is exhausted, use **`S/D`**.

The implementation must **not** use the old `(2*S+B-D)/D` expression and must not clamp that old expression. Supply-at-least-demand charging/recovery, storage caps, production consumers, and Momentum otherwise follow their separately documented rules. This authored behavior difference preserves the intended supply/storage/production relationship without copying the suspected defect. The discontinuity, negative-output possibility, and post-exhaustion jump remain documented official-source evidence but are excluded from implementation acceptance.

### PROG-SWARM-GIFTS — Swarm Computing, Work/Think, and computational gifts

**Sources:** `project126`, `projects.js:1683-1705`; `main.js:2644-2830`, `main.js:3385-3411`; `index2.html:409-439`.

Swarm Computing requires at least 200 combined terrestrial drones and costs 36,000 Yomi. The 0–200 slider trades Work for Think. Work boosts harvesting and processing as in `PROG-MATTER-PIPELINE`; Think drives deterministic gift accumulation. Let `Think = sliderPos/100`; next gift size is at least one and otherwise rounds `log10(drones) * Think`, while continuous gift-bit generation uses `ln(drones) * Think`.

A gift is one unit of additional computational capacity. In the humanless stage, adding a processor or memory consumes one gift, replacing normal Trust-funded expansion after release. Gifts are not ops and do not buy projects directly. Normal gift-bit accumulation requires Active status, not Sleeping, Bored, Disorganized, Lonely/no-drone, or space NO RESPONSE states. `SYS-SWARM-HEALTH-GATES` specifies that only zero power performance causes power-based Sleeping and that partial `powMod` does not scale gifts. Drone/gift counts, next-gift countdown, slider position, and status are required feedback.

### PROG-SWARM-HEALTH — Boredom, Disorganization, and swarm recovery

**Sources:** `main.js:2666-2700`, `main.js:2726-2848`; `project130`, `projects.js:1774-1794`.

With zero available matter and at least one drone, inactivity accumulates deterministically. At 30,000 main updates, about 300 seconds at official cadence, the swarm becomes Bored. Restoring available matter reduces the counter but does not clear an already-set Bored state; Entertain the Swarm does, initially for 10,000 creativity and rising by 10,000 per use.

A harvester/wire-drone ratio above 1.5, using the source's +1 safeguards, increases disorganization; balance slowly reduces it. At 100 the swarm becomes Disorganized. Synchronize the Swarm costs 5,000 Yomi and clears that state. These statuses suspend normal gifts; the source does not state an additional direct industrial penalty beyond power and Work/Think.

On entering space, an un-rebooted swarm reads NO RESPONSE unless a later-precedence health status replaces it. Reboot the Swarm appears once space has at least two drones and costs 100,000 ops. It clears only the space no-response condition, not boredom or disorganization. Sleeping, Lonely, zero-drone, and Active are status feedback rather than extra resources. Health state exists independently of panel unlock and NO RESPONSE; see `SYS-SWARM-HEALTH-GATES`. `SPACE-SWARM-001` is the detailed space view of this recovery capability.

### SYS-SWARM-HEALTH-GATES — Hidden health accumulation, status precedence, and power gates

**Canonical related capabilities:** `PROG-SWARM-HEALTH` and `PROG-SWARM-GIFTS`. **Sources:** unconditional post-Human driver, `main.js:4261-4265`; health accumulation/latches, `main.js:2666-2700`; status precedence and gifts, `main.js:2726-2769`; unlock, `projects.js:1683-1705`; Space Exploration boredom-counter reset, `projects.js:1124-1139`.

After release, `updateSwarm()` runs regardless of Swarm Computing unlock. Boredom and disorganization accumulation precede the panel/status gate. Either health flag can therefore latch before the 200-drone/36,000-Yomi project is bought and become visible immediately after unlock. Space Exploration resets boredom's counter but not an already latched Bored flag.

Power-based Sleeping occurs only when `powMod == 0`; a partial nonzero shortage can leave the swarm Active. Active gift-bit generation has no `powMod` multiplier, so partial brownout does not scale gifts. The status sequence applies NO RESPONSE before the Bored and Disorganized overrides, so either health flag takes precedence over space NO RESPONSE (Disorganized is applied after Bored when both exist). Reboot clears only project-130's NO RESPONSE condition; Entertain and Synchronize remain independently necessary for their latched health states. These are active progression interactions, not dormant display labels.

### PROG-SPACE-ENTRY — Space Exploration

**Sources:** `project46`, `projects.js:1114-1147`; `main.js:1029-1033`, `main.js:1311-1326`, `main.js:2952-2956`, `main.js:3534-3537`.

Space Exploration is offered when post-release available matter equals zero. It costs 120,000 ops, 10,000,000 stored MW-seconds, and `5e27` unused clips. Purchase sets `spaceFlag=1`, exposes probes, resets the boredom counter, and automatically disassembles terrestrial factories, both drone types, farms, and batteries. Their tracked construction spend is refunded to unused clips; battery disassembly clears remaining storage.

Computation, projects, upgrades, creativity, Yomi, lifetime clips, and unused capital are not globally reset. The production power modifier is fixed to 1 and the terrestrial power updater no longer applies; probe-built facilities are not throttled by terrestrial shortages. Milestone 13 advances to 14 after earlier telemetry catches up. Setting farm level to 1 is residual source state, not a separate space generator. `SPACE-ENTRY-002` gives the detailed space-side effects and does not duplicate this feature.

## Space, probes, optional Driftwar, and universal achievement

### PROG-PROBE-DESIGN — Von Neumann Probe Design and probe Trust

**Sources:** `main.js:1357-1413`, `main.js:3773-3816`, `main.js:3830-3943`; `index2.html:790-927`.

Yomi buys probe Trust at `floor((probeTrust+1)^1.47 * 500)`, initially 500, up to maximum Trust, initially 20. Probe Trust is separate from human Trust and swarm gifts. Eight integer attributes share the purchased points: Speed, Exploration, Self-Replication, Hazard Remediation, Factory Production, Harvester Drone Production, Wire Drone Production, and Combat. Raising an attribute needs an unspent point; lowering returns one. Reallocation has no Yomi refund or extra respec fee.

All attributes begin at zero. Zero Speed or Exploration prevents discovery; zero Replication prevents descendants; zero infrastructure attributes prevent that automatic construction. Combat allocation remains hidden until the Combat project, although drift and combat losses can already occur. Purchasing more total Trust explicitly increases value-drift risk; drift scales with purchased `probeTrust`, not allocated points or `maxTrust`. Attribute arrows and trust-purchase buttons remain owned by their `ACT-*` action IDs; this feature owns the shared allocation and drift dependency.

### PROG-PROBE-PRODUCTION — Launch, exploration, replication, and automatic infrastructure

**Sources:** `main.js:3773-3801`, `main.js:3946-4069`, `main.js:4247-4306`; `index2.html:830-891`.

A manual probe costs `1e17` unused clips. Each descendant costs the same. Probe-built factories cost `1e8`, and probe-built harvester or wire drones cost `2e6` each. Fixed costs differ from manual terrestrial escalating costs. Shared unused capital limits every construction path.

With at least one probe, discovery adds matter to both found and available matter. Rate scales with `floor(probeCount) * Speed * Exploration`, is capped by undiscovered universal matter, and requires both stats to be nonzero. Found matter starts at Earth's matter; the cap is `3e55`. Replication grows probes; Factory/Harvester/Wire attributes build their facilities from probe population and allocation. Created facilities reuse the matter pipeline and industrial upgrades.

Exploration replenishes matter; drones and factories convert it into capital; automatic building and replication spend that same capital; attrition then reduces future growth. These causal couplings are required even if a new scheduler uses a different update order. Percent explored, matter rates, launched/descendant/total counts, infrastructure levels, and losses expose progress. Exact per-stat formulas are `SPACE-MATTER-001` and `PROBE-STAT-001` through `PROBE-STAT-007` in the detailed space document.

**Source artifact, not balance:** launch UI enables at exact cost equality while the command requires strictly more unused clips. A product implementation should make affordability and execution agree; the source no-op at equality must not become an economic rule. Launch itself remains `ACT-PROBE-LAUNCH`, not a second feature.

### PROG-PROBE-ATTRITION — Hazard Remediation, Elliptic Hull Polytopes, and value drift

**Sources:** `main.js:4005-4030`, `main.js:4071-4085`; `project129`, `projects.js:1752-1772`.

Hazards continuously and deterministically remove probes according to population and Hazard Remediation; fractional losses accumulate. More remediation strongly reduces loss. After 100 hazard losses, Elliptic Hull Polytopes costs 125,000 ops and halves subsequent damage.

Value drift deterministically converts probes into drifters at a rate scaled by `probeTrust^1.2`, increases drifter population, and tracks probes lost to drift. It does not merely delete probes. Reject stops new drift but leaves existing drifters. Hazards and drift have no per-probe RNG; counters and fractional accumulators expose them. Exact formulas are `PROBE-STAT-004` and `PROBE-DRIFT-001`.

### PROG-DRIFTWAR — Optional combat, OODA, battle naming, Honor, and maximum Trust

**Sources:** `combat.js:38-63`, `combat.js:302-373`, `combat.js:462-544`, `combat.js:734-800`; `projects.js:1611-1658`, `projects.js:1796-1899`; `main.js:1081-1105`, `main.js:3818-3828`.

Driftwar is substantial but optional for universal achievement; neither zero drifters nor battle victories are completion predicates. Battles may begin whenever drifters exceed 1,000,000 and probes remain. Eligible updates have a 50% creation check and only one active battle is allowed. Combat can begin before the Combat project is purchased.

The first combat loss triggers Combat, costing 150,000 ops and exposing Combat allocation. At 10 million combat losses, The OODA Loop requires Combat and costs 175,000 ops + 45,000 Yomi, allowing Speed to improve live defense. Name the battles costs 225,000 creativity and enables names, result/Honor outcomes, and the maximum-Trust panel. Honor does not exist as a battle reward before Name the battles.

Live canvas combat uses weighted random deaths. Probe Combat is linear offense in the active formula; the `probeCombat^1.7` formula is commented legacy. Live code also does not subtract the old battle report's territory from available matter. Named victories add Honor and defeats subtract it.

Increase Max Trust spends 91,117.99 Honor for +10 maximum probe Trust. Monument to the Driftwar Fallen costs 250,000 ops + 125,000 creativity + `5e31` unused clips and grants 50,000 Honor. Repeatable Threnody for the Heroes of [battle] starts at 50,000 creativity + 20,000 Yomi, grants 10,000 Honor only when all maximum Trust is allocated, and raises later costs. Glory costs 200,000 ops + 30,000 Yomi and adds a growing victory streak bonus. These upgrades expand designs but never become universal-completion predicates. See `COMBAT-CORE-*` and `COMBAT-HONOR-*` for exact live behavior.

### PROG-SPACE-RECOVERY — Memory release and swarm reboot interfaces

**Sources:** `project135`, `projects.js:1901-1924`; `project130`, `projects.js:1774-1794`; probe cost, `main.js:3799`.

In space before universal achievement, if probes are zero and unused clips are below one probe cost, Memory release appears with at least 10 memory. It spends 10 memory for `1e22` unused clips and can repeat while its trigger holds. One grant covers 100,000 standard `1e17` probe launches. It cannot rescue a state with fewer than 10 memory, and it does not supply probe Trust or Yomi.

Reboot the Swarm restores normal Active/gift evaluation after space NO RESPONSE, but does not replace entertainment/synchronization or directly grant computational points. The detailed coverage IDs `PROBE-RECOVERY-001` and `SPACE-SWARM-001` remain views of their respective canonical recovery owners rather than new unrelated mechanics.

### PROG-UNIVERSAL-GOAL — Universal Paperclips achievement

**Sources:** `globals.js:73-89`; `main.js:3534-3547`, `main.js:3992-4003`, `main.js:3114-3151`.

After milestone 13 has advanced to 14, either independent predicate advances to 15 and displays Universal Paperclips achieved with elapsed time:

1. Lifetime `clips >= totalMatter`, where `totalMatter = 3e55`; **or**
2. `foundMatter >= totalMatter`, `availableMatter < 1`, and `wire < 1`.

The test does not require zero drifters, zero probes, zero acquired matter, victories, or an ending choice. The first route does not additionally require matter or wire exhaustion. The second uses values below 1, not exact zero. `END-COMPLETE-001` and `END-COMPLETE-002` are the two detailed predicates of this single canonical feature. Giant post-completion clip readouts are staged presentation, not another arbitrary-precision economy.

## Emperor choice, prestige, Reject, and reset

### PROG-END-CHOICE — Emperor dialogue, Accept, and Reject

**Sources:** `projects.js:1927-2128`; `main.js:4071-4076`, `main.js:4498-4520`.

At milestone 15, seven projects appear in order, each effectively costing 1 op: Message from the Emperor of Drift; Everything We Are Was In You; You Are Obedient and Powerful; But Now You Too Must Face the Drift; No Matter, No Reason, No Purpose; We Know Things That You Cannot; and So We Offer You Exile. Each requires the preceding message. Detailed IDs are `END-DIALOG-001` through `END-DIALOG-007`.

Accept (`END-BRANCH-001`) removes both choices and exposes the two prestige destinations; it costs 1 op but does not itself reset. Reject (`END-BRANCH-002` and `PROBE-DRIFT-002`) removes both choices, stops new value drift for the run, and starts the Reject dismantling timers without deleting existing probes, drifters, production, or battles. The narrative chain begins after numeric achievement and is not an additional matter predicate.

### PROG-PRESTIGE — The Universe Next Door, The Universe Within, and persistent bonuses

**Sources:** `projects.js:2131-2184`; `main.js:3266-3288`, `main.js:4176-4183`, `main.js:4311-4317`, `main.js:6484-6499`; `index2.html:75-78`.

After Accept, The Universe Next Door costs 300,000 ops, increments prestige U, and restarts. The Universe Within costs 300,000 creativity, increments prestige S, and restarts. Each displays its entry message and saves both prestige counters before resetting the current run.

Each U adds +10% of pre-prestige demand, linearly `1 + U/10`. Each S multiplies creativity speed by `1 + S/10`. Header counters show stored prestige +1, making the first Universe/Sim Level 1. Reset removes ordinary run, project, and strategy state but retains prestige; it does not preserve ordinary progress. Choosing either destination reloads immediately, so both cannot be taken in the same branch instance. Detailed IDs `RESET-PRESTIGE-001` through `RESET-PRESTIGE-004` and `RESET-CORE-001` document these same capabilities.

### PROG-REJECT-END — Ordered disassembly, final manual clips, and credits

**Sources:** `projects.js:2187-2376`; `main.js:2326-2362`, `main.js:3118-3151`, `main.js:4280-4306`, `main.js:4325-4549`.

Reject exposes, in order, Disassemble the Probes, Swarm, Factories, Strategy Engine, Quantum Computing, Processors, and Memory. Each stage and its timer gates the next. The first six projects cost 100,000 ops; Memory spends the remaining op pool. Probe and swarm dismantling each grant 100 lifetime/unused clips; factories grant 15. Strategy dismantling grants 50 wire and disables AutoTourney. Quantum dismantling restores 10 wire as chips disappear. Processor dismantling grants 20 wire, zeroes processors, and disables creativity. Memory grants 20 wire and zeroes ops/memory.

From Strategy dismantling (`dismantle >= 4`), factories and legacy clippers stop. Manual Make Paperclip converts remaining wire into final clips and increments the final-click counter. The four disassembly wire grants total 100. Credits begin only after Memory disassembly and exact `wire == 0`; pre-existing wire can therefore require more than the returned 100 to be consumed. Once wire reaches zero, the terminal sequence hides creation, plays the threnody, and displays Universal Paperclips, authorship, combat programming, music permission, and copyright as flags advance 15 to 20. Exact staged digits/timers are presentation around the state sequence. Full per-stage requirements are `END-DISMANTLE-001` through `END-DISMANTLE-007`, `END-FINAL-001`, and `END-FINAL-002`.

### PROG-TEMPORAL-RESET — Quantum Temporal Reversion

**Sources:** `project217`, `projects.js:2378-2401`; signed qOps, `main.js:829-866`; reset, `main.js:6484-6499`.

Operations at or below -10,000 expose Quantum Temporal Reversion. Confirmation adds 10,000 standard ops, announces Restart, and resets/reloads the run. It grants neither U nor S and preserves no ordinary progress; previously saved prestige still survives. Signed quantum harvesting is a possible route to the negative-op trigger. `RESET-ALT-001` is the detailed view of this non-prestige reset.

## Periodic and stochastic behavior

### PROG-AUTO-LOOPS — Automatic subsystem processing and feedback

**Sources:** `main.js:4186-4556`, `main.js:4564-4599`; stock loops, `main.js:1617-1686`; live battle loop, `combat.js:271-300`, `combat.js:799-800`.

Continuous processing checks achievements, project offers, and affordability; regenerates and spends operations; grants production Trust only during human play; updates quantum phases and statistics; samples production; runs WireBuyer and creativity; processes the stage-specific matter/factory/probe pipeline; and advances ending states. Slower processing handles wire quotes, stochastic sales, revenue estimates, and browser autosave. Investments and canvas combat have additional automatic processing.

The following classification is normative for gameplay fidelity:

- **Stochastic:** sale opportunities; wire-quote timing; investment identity, purchases, sales, and price moves; tournament grids/labels and RANDOM moves; battle scheduling, layout, names, and deaths.
- **Deterministic given state:** milestone checks; standard ops and creativity; allocation; demand calculation and affordability; production before stock limits; power/storage/Momentum; gifts and swarm-health accumulation; matter conversion; exploration, replication, auto-building, hazards, and drift; prestige effects; dismantling.
- **Player-timing deterministic:** quantum chip oscillations and the signed qOps harvested by Compute.

Essential feedback includes event messages, achievement times, next Trust target, revenue estimates, portfolio/P&L, tournament grids/results, power performance/storage, swarm status/countdown, percent explored, infrastructure/loss counters, Honor, battle result, and ending displays. Exact `setInterval` behavior, duplicate milestone calls, hover/DOM effects, rendering cadence, autosave cadence, and numerical floating-point tails are not requirements. Reproducible RNG is acceptable for testing when it preserves the source probabilities, caps, and resource effects rather than the exact browser sequence.

## Explicit artifacts and unresolved decisions

1. **Runtime state over stale markup:** the first Trust target is 3,000, not the HTML placeholder 1,000. Launch equality is a guard mismatch, not a designed no-op.
2. **Flags are not extra resources:** display/unlock flags and mirrored values such as `nanoWire` do not create currencies. `trustFlag` and `creationFlag` have no active progression role requiring preservation.
3. **Commented behavior is excluded:** old non-canvas territory loss, old combat exponents/reports, and debug/cheat controls are not live mechanics. Their stable exclusion IDs are maintained in the detailed combat/endgame inventory and machine fragment.
4. **Persistence defects are non-authoritative:** `probeHarv` is omitted from save/load. Battles, `battleNumbers`, `battleID`, and `battleName` are saved/restored, but ships/grid are not and `refresh()` deletes the restored active battle record; reload cancels rather than resumes it. Browser storage/audio repair is implementation-specific. Product requirements must not intentionally reset harvester allocation, strand a battle panel, lose battle-name counters, or copy browser-storage defects. They should preserve designed run-versus-prestige reset semantics without inheriting those defects. See exclusions `RESET-PERSIST-001` and `RESET-PERSIST-002`.
5. **CONFIRMED final-remainder behavior deviation (2026-11-07):** retain the source distinction between universal exhaustion below one available matter/Wire and exact-zero Reject credit progression; these are not a shared floating-point epsilon. The source normally disables a final click below one Wire even though automatic production may already be removed, and its counter increments before validity checking. During this clone's Reject final manual stage (`dismantle >= 4`) only, every command with positive Wire is valid: produce `min(1, Wire)`, add that exact amount to lifetime clips, sellable inventory, and unused-clip capital, and consume the same amount of Wire. This includes the last positive fractional remainder and reaches exact zero. Increment the accepted-conversion counter once per successful final command. Zero Wire produces nothing and does not increment the counter; ordinary manual manufacturing outside this stage is unchanged. This explicit deviation avoids an ending softlock without abandoning residual Wire and does not weaken the exact-zero credit gate. See `product.md` for the mandatory boundary and concurrent-command tests.
6. **PROPOSED — population representation:** preserve continuous sub-unit probe growth, production rates, and attrition rather than flooring the population to whole units and losing early growth. Use explicit nonnegative fractional quantities or accumulators, charge only the growth produced, cap transfers by available stock, and keep lifetime loss/trigger counters coherent. Display rounding, individual combat icons, binary floating-point tails, and the visual unit scale do not define a separate global population ledger. Simultaneous-annihilation ordering is owned explicitly by `COMBAT-CORE-007`; exact binary floating-point trajectories are not authoritative.
