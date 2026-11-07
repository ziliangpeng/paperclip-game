# Gameplay Combat, Probes, Space, Endgame, and Resets

## Scope, ownership, and evidence

This document preserves all 68 detailed coverage IDs from the combat/probe/endgame research. It specifies active world simulation, outcomes, information feedback, narrative progression, and reset semantics. It does not duplicate button inventories and it is not a milestone plan.

Evidence locators refer to the official issue #3 source snapshot. Public official URLs and source hashes belong to that snapshot; no local capture path is part of this repository reference. JavaScript names are source locators, not required implementation names.

Canonical high-level progression owners are in [gameplay progression](gameplay-progression.md). Direct HTML commands are in [actions and controls](gameplay-actions.md); individual project prices/offers are in the [project catalog](gameplay-projects.md). An ID below may provide exact detail for one of those canonical capabilities without becoming a second feature in `features-systems.json`. Independent simulation and state-transition capabilities are included once in the machine fragment.

### Conventions and fidelity boundary

- `P` means global `probeCount`; `D` means global `drifterCount`; `U` is an independent uniform draw in `[0,1)` when a formula uses it.
- Formulas stated “per main update” use the source's nominal 10 ms update. Canvas formulas use its nominal 16 ms update. These intervals explain source pacing but are not required architecture; preserve normalized rates, interactions, and stochastic consequences.
- **Source fact** distinguishes observed live behavior from project prose. **Artifact** identifies implementation-only or defective behavior not to import. **OPEN** records an unresolved product interpretation rather than silently balancing it.
- Large-number spelling, exact pixels, frame timing, floating-point residue, and duplicated DOM updates are presentation or implementation, not separate mechanics.

## State flow and dependency contracts

Exploration runs before the matter conversion chain. Factories then turn wire into all three clip ledgers. In the space block, hazards precede factory, harvester, and wire-drone auto-building, then self-replication, value drift, and battle scheduling. Newly built units affect later updates; newly replicated probes can be included in that update's drift; drift can make a battle eligible immediately. Canvas combat advances independently. Preserve these causal dependencies without copying browser timer jitter.

| State | Producer and consumer contract |
|---|---|
| Probe population | Manual launch and replication increase it; hazards, drift, canvas casualties, and Disassemble the Probes reduce it. It drives discovery, building, replication, drift, and battle scale. |
| Drifter population | Only value drift creates drifters; canvas combat kills them. Reject stops new drift but does not delete existing drifters or battles. |
| Unused clips | Shared capital pays for launches, descendants, auto-built facilities, and selected projects. Spending does not reduce lifetime clips. |
| Matter chain | Discovery adds to found and available matter. Harvesting moves available to acquired; processing creates wire; clip conversion creates lifetime, unsold, and unused clips. |
| Probe Trust / stats | Yomi buys total probe Trust; eight attributes allocate it. Purchased Trust drives drift; allocated stats drive simulation. Combat allocation directly kills drifters; Speed with OODA defends. |
| Combat losses | Real canvas casualties increment combat losses and unlock Combat after the first, OODA and Name the battles after 10 million. Drifters Killed is feedback, not the victory Honor basis. |
| Battle state | One active battle is allowed. First attack permanently reveals combat UI. Ships are visual simulation entities whose deaths alter global populations. |
| Honor | Named victories/defeats and Honor projects change it. It buys maximum probe Trust; defeat chooses a threnody title and resets Glory's bonus. |
| Ending state | Milestone 14/15, Emperor project flags, disassembly stage, final clicks, and exact-zero wire drive the branch and credits. |
| Prestige | U and S are saved separately from an ordinary run; U modifies human demand and S modifies creativity. |

### Negative source contracts

- Live canvas combat never applies old battle-report territory loss to available matter.
- Live attrition uses global `P` and `D`, not opening `clipProbes` or `drifterProbes` fields.
- Live probe offense against drifters is linear in `probeCombat`; the `probeCombat^1.7` expression is commented legacy.
- `processedMatter` is not a live inventory. No additional stock should be inserted between acquired matter and wire.
- There is no start, stop, retreat, or tactical battle button. Active player influence is design allocation and related projects.

## Entry into space and the matter economy

### SPACE-ENTRY-001 — Release the HypnoDrones transition

**Canonical progression owner:** `PROG-HYPNO-RELEASE`. **Sources:** `projects.js:711-750`, `project35`; `main.js:1260-1273`.

Release costs 100 Trust after HypnoDrones. It sets `humanFlag=0`, clears Trust and manual clippers, removes the human Business/Manufacturing/Trust interfaces, and exposes autonomous production of Earth's resources. Offered Xavier Re-initialization is removed. This deterministic state change, not the visual overlay, is the transition. Exact terrestrial prerequisites belong to `PROG-HYPNO-RELEASE` and the project catalog.

### SPACE-ENTRY-002 — Space Exploration transition and refunds

**Canonical progression owner:** `PROG-SPACE-ENTRY`. **Sources:** `projects.js:1114-1147`, `project46`; `main.js:1023-1033`, `main.js:1311-1326`, `main.js:3534-3537`.

After release and zero available Earth matter, Space Exploration costs 120,000 ops, 10,000,000 MW-seconds, and `5e27` unused clips. It sets `spaceFlag=1`, enables probe systems, announces “Von Neumann Probes online,” dismantles terrestrial factory/drone/power facilities, and refunds their tracked construction bills to unused clips. Battery teardown clears storage. One farm remains as residual state, while production power is fixed to 1 and the pre-space power simulation is disabled.

Manual terrestrial build controls give way to space counts and automatic construction. Ordered milestone 13 records full terrestrial utilization and becomes 14 when earlier telemetry has caught up. Audio preloading is a browser artifact; the cost, refunds, retained progression, and full-power space production are design behavior.

### SPACE-MATTER-001 — Universe explored and Available Matter

**Detailed world system under:** `PROG-PROBE-PRODUCTION`. **Sources:** `globals.js:73-89`; `exploreUniverse`, `main.js:3992-4003`; `index2.html:224-250`.

Total universal matter is `3e55`. Initially found and available matter are both `6e27`. With at least one probe, deterministic discovery per main update is:

`floor(P) * 1.75e18 * probeSpeed * probeNav`

The result is capped by undiscovered matter and added to both found and available matter. Fractional probe population does not contribute because `P` is floored. Either Speed or Exploration at zero yields no discovery. Discovered/available matter, discovery rate, and percent explored are required feedback.

### SPACE-MATTER-002 — Harvester Drones and Acquired Matter

**Detailed world system under:** `PROG-MATTER-PIPELINE`. **Sources:** `main.js:4105-4138`; `projects.js:1491-1558`, `project110`-`project112`; `index2.html:150-155`, `index2.html:215-220`.

During autonomous play, harvesting moves available matter to acquired matter, capped by availability. Base request per main update is:

`powMod * floor(harvesterLevel) * 26,180,337 * ((200-sliderPos)/100)`

Adversarial Cohesion adds another `droneBoost * floor(harvesterLevel)` multiplier, producing quadratic scaling in harvester count. At least one harvester and available matter are required for nonzero output. Acquired stock and acquisition/sec expose the bottleneck. **Source-grounded rule:** the live code uses this quadratic scaling and it must be preserved. It must not be flattened merely because one project label sounds like a flat bonus; only an explicit product-authorized balance change could replace it.

### SPACE-MATTER-003 — Wire Drones and Wire

**Detailed world system under:** `PROG-MATTER-PIPELINE`. **Sources:** `main.js:4140-4169`; `projects.js:1491-1558`; `index2.html:152-155`, `index2.html:215-220`.

Wire drones convert acquired matter to wire numerically 1:1, capped by acquired stock. Base request per main update is:

`powMod * floor(wireDroneLevel) * 16,180,339 * ((200-sliderPos)/100)`

Adversarial Cohesion adds the analogous level multiplier. At least one wire drone and acquired matter are required. Wire and wire/sec are required feedback. `processedMatter` is initialized/saved but not updated by live processing and is excluded as a second inventory.

### SPACE-MATTER-004 — Factories and clip production

**Detailed world system under:** `PROG-MATTER-PIPELINE` and `PROG-INDUSTRY-UPGRADES`. **Sources:** `main.js:2326-2362`, `main.js:4271-4282`; `projects.js:1421-1488`; `index2.html:130-136`.

Base factory request per main update is `powMod * floor(factoryLevel) * 1e9`, capped by wire. Factory upgrade multipliers apply before the cap; Self-correcting Supply Chain introduces an additional factory-level factor rather than only a flat bonus. Actual output increases lifetime, unsold, and unused clips equally. Space Exploration sets `powMod=1`. Production stops when `dismantle>=4`.

The active multiplier stack, including quadratic upgraded scaling, is source behavior. Exact display rounding is not.

### SPACE-MATTER-005 — Work/Think and fixed space production power

**Detailed world system under:** `PROG-POWER` and `PROG-SWARM-GIFTS`. **Sources:** `index2.html:432-438`; `main.js:2644-2653`, `main.js:2952-3058`, `main.js:4105-4169`; `projects.js:1124-1140`.

The shared slider scales harvesting and wire processing by `(200-sliderPos)/100`: full Work (0) gives ×2, midpoint gives ×1, and full Think (200) gives ×0. The same control drives swarm gift generation; these are not separate allocations.

The power updater runs only before space. Space Exploration fixes `powMod=1`, so terrestrial power shortages do not throttle space matter conversion or factories. Matter conversion continues while the swarm says NO RESPONSE until Reboot the Swarm; that status gates normal gifts, not the Work/Think multiplier. **Non-goal:** a product may improve how this shared allocation is presented, but it must not create independent space and swarm Work/Think resources. One allocation drives both behavior families.

### SPACE-SWARM-001 — Reboot the Swarm in space

**Canonical progression owner:** `PROG-SWARM-HEALTH` and `PROG-SPACE-RECOVERY`. **Sources:** `project130`, `projects.js:1774-1794`; `main.js:2726-2772`, `main.js:2824-2826`.

Space forces an otherwise operational swarm into NO RESPONSE until Reboot is purchased for 100,000 ops. The project is available in space with at least two combined harvester/wire drones. It restores normal status evaluation, allowing Active status and gifts when no higher-priority condition applies. It does not directly change probe stats, matter rates, boredom, or disorganization. The project-flag mechanism is replaceable; the selective recovery contract is gameplay.

## Probe creation, allocation, statistics, losses, and recovery

### PROBE-CREATE-001 — Launch Probe population seed

**Canonical action owner:** `ACT-PROBE-LAUNCH`; progression dependency: `PROG-PROBE-PRODUCTION`. **Sources:** `main.js:3773-3803`, `main.js:3946-3959`; `index2.html:232-250`.

A launch spends `1e17` unused clips, adds one probe, and increments the manual-launch counter; descendants are separate. This cost is constant despite obsolete commented formulas. **Artifact:** the action requires strictly more than cost while the button enables at equality. Equality is a source no-op defect, not a rule that prices or costs should be rebalanced. The machine fragment does not create a second feature for this already-owned HTML action.

### PROBE-TRUST-001 — Increase Probe Trust economy

**Canonical action owner:** `ACT-PROBE-TRUST-INCREASE`; progression dependency: `PROG-PROBE-DESIGN`. **Sources:** `main.js:3801-3816`; `index2.html:790-799`, `index2.html:917-921`.

In space, Yomi buys one probe-Trust point up to `maxTrust`, initially 20. Displayed cost follows `floor((probeTrust+1)^1.47 * 500)` and starts at 500. Purchase warns “Risk of value drift increased.” Purchased `probeTrust` increases drift; merely increasing maximum Trust does not. The action ID owns the direct HTML control.

### PROBE-DESIGN-001 — Shared Von Neumann Probe allocation

**Canonical progression owner:** `PROG-PROBE-DESIGN`; direct arrows are the `ACT-PROBE-*` action family. **Sources:** `main.js:1357-1413`, `main.js:3830-3943`; `index2.html:790-927`.

Eight integer stats share purchased probe Trust: Speed, Exploration, Self-Replication, Hazard Remediation, Factory Production, Harvester Drone Production, Wire Drone Production, and Combat. Raising needs an unspent point; lowering above zero returns it. Allocation is freely reversible without Yomi refund or respec fee. Used/current/max Trust are visible. Maximum starts at 20. Combat arrows additionally require the Combat project. Allocation is not consumed by launching or construction.

### PROBE-STAT-001 — Speed simulation effects

**Sources:** `main.js:3775-3777`, `main.js:3830-3845`, `main.js:3992-4003`; `combat.js:478-480`, `combat.js:507-518`; `index2.html:802-813`.

Speed multiplies discovery together with Exploration. After The OODA Loop, it also adds defense to the live probe-casualty threshold. Speed allocation changes a parallel `attackSpeed` variable, but live canvas combat does not read that variable; it reads `probeSpeed`. Both discovery and OODA defense are active roles. Assignment is deterministic; combat consequences are stochastic.

### PROBE-STAT-002 — Exploration simulation effect

**Sources:** `main.js:3776-3777`, `main.js:3847-3859`, `main.js:3992-4003`; `index2.html:817-828`.

Exploration (`probeNav`) multiplies discovery together with Speed. Zero Exploration or zero Speed means no newly found matter. It consumes one allocatable point per level and has no separate per-discovery resource cost.

### PROBE-STAT-003 — Self-Replication and descendant growth

**Sources:** `main.js:3778-3780`, `main.js:3875-3887`, `main.js:3961-3990`; `index2.html:830-841`.

With an existing probe and Replication allocation, desired descendants per main update are:

`P * 0.00005 * probeRep`

Each costs `1e17` unused clips. If the desired growth exceeds affordable capital, it is clipped afterward to `floor(unusedClips/1e17)` whole probes. Growth stops near `1e48` probes.

For `0 < nextGen < 1`, the source also adds `nextGen` to `partialProbeSpawn`. When that accumulator reaches 1, the current update's growth becomes one descendant and the accumulator resets. On other sub-one updates, however, sufficient capital still allows the current fractional `nextGen` itself to be added to descendant and total populations. This is not deferred whole-probe-only growth. Descendants, total probes, and unused capital are required feedback. **PROPOSED representation:** preserve the observed fractional descendant growth when the fractional amount is affordable; an implicit whole-probe floor would lose real early growth. Use continuous nonnegative quantities or explicit accumulators, and charge only the descendant amount actually created. Preserve caps, lifetime counters, and causal ordering without requiring the original binary floating-point residue, partial-spawn variable name, or mutable combat icon scale. A larger stock cannot be spent on an unproduced descendant, and small-population losses must not produce negative population.

### PROBE-STAT-004 — Hazard Remediation and hazard losses

**Sources:** `main.js:3781-3786`, `main.js:3861-3873`, `main.js:4005-4030`; `projects.js:1752-1772`, `project129`; `index2.html:843-854`.

Deterministic hazard loss per main update is:

`P * 0.01 / (3 * probeHaz^1.6 + 1)`

Elliptic Hull Polytopes halves the request. Immediate losses in the `amount >= 1` branch are capped at `P`. Smaller amounts accumulate in `partialProbeHaz`; reaching 1 removes one probe and increments lifetime hazard losses. More Remediation reduces rather than creates losses. The loss counter appears after the first loss. Elliptic Hull Polytopes costs 125,000 ops and unlocks after 100 hazard losses.

**Artifact:** when an accumulated one-probe loss fires with `P < 1`, source clamps population to zero but still adds one to the loss counter. That potential counter excess is not an intended extra casualty rule. Accumulator precision and this low-population edge are not invariants; keep population and loss accounting coherent.

### PROBE-STAT-005 — Factory Production auto-building

**Sources:** `main.js:3787-3788`, `main.js:3889-3901`, `main.js:4032-4043`; `index2.html:856-867`.

In space, desired factory growth per main update is:

`P * 0.000001 * probeFac`

Each costs `1e8` unused clips and growth is affordability-limited. Existing probes, allocation, and capital are required. Auto-built factories do not increment manual terrestrial `factoryBill` and do not use its escalating price curve. Their output uses `SPACE-MATTER-004`.

### PROBE-STAT-006 — Harvester Drone Production auto-building

**Sources:** `main.js:3789-3790`, `main.js:3903-3915`, `main.js:4045-4056`; `index2.html:869-880`.

Desired growth per main update is `P * 0.000002 * probeHarv`. Each harvester costs `2e6` unused clips, with affordable whole-unit clipping. These harvesters feed `SPACE-MATTER-002` and reuse existing upgrades. **Artifact:** the official save variants omit `probeHarv`; losing this allocation on reload is excluded by `RESET-PERSIST-001`, not an intended attrition or respec mechanic.

### PROBE-STAT-007 — Wire Drone Production auto-building

**Sources:** `main.js:3791-3792`, `main.js:3917-3929`, `main.js:4058-4069`; `index2.html:882-893`.

Desired growth per main update is `P * 0.000002 * probeWire`. Each wire drone costs `2e6` unused clips and is affordability-limited. The resulting drones feed `SPACE-MATTER-003`. Growth uses the shared population/capital model, not manual terrestrial build prices.

### PROBE-STAT-008 — Combat allocation and direct offense

**Sources:** `main.js:3931-3943`; `project131`, `projects.js:1796-1816`; `combat.js:462-540`; `index2.html:896-911`.

The Combat project costs 150,000 ops after one combat loss and reveals the allocation row. Each Combat point increases the live drifter-death roll linearly. It does not directly reduce the probe-death roll; OODA-modified Speed supplies direct defense. Battles and initial losses can occur before this project is purchased.

**Source fact versus prose:** the tooltip says “offensive and defensive effectiveness,” but active code supplies direct offense only. Any defense is indirect through killing drifters faster. **PROPOSED rule and feedback:** preserve the active direct-offense formula; higher Combat kills Drifters faster and defends only indirectly, while OODA-modified Speed supplies direct defense. Best-effort UI wording must describe this actual relationship rather than promise a hidden direct-defense term. Do not import the commented exponent or silently add a new Combat-to-survival reduction.

### PROBE-DRIFT-001 — Value drift creates Drifters

**Sources:** `main.js:3794-3797`, `main.js:4071-4085`; `combat.js:39`, `combat.js:55-63`; `index2.html:245`, `index2.html:253-256`.

Per main update, drift converts:

`P * 0.000001 * probeTrust^1.2`

probes into drifters, capped at `P`. It increases lifetime drift loss and current Drifters simultaneously. Higher purchased Trust therefore has a deterministic drawback even when points are unspent. Drifters can trigger attacks once `D>1,000,000` and `P>0`. Source populations can be fractional; there is no random per-probe drift roll.

### PROBE-DRIFT-002 — Reject permanently stops new drift

**Canonical branch owner:** `END-BRANCH-002`; progression owner: `PROG-END-CHOICE`. **Sources:** `project148`, `projects.js:2106-2128`; `main.js:4071-4076`, `main.js:4498-4500`.

Reject sets subsequent drift to zero for the current run and starts ending timer 1. It does not remove existing drifters or force an ongoing battle to end. “Permanently” applies until a run reset; it is not a meta-prestige effect.

### PROBE-RECOVERY-001 — Memory release anti-softlock recovery

**Canonical progression owner:** `PROG-SPACE-RECOVERY`. **Sources:** `project135`, `projects.js:1901-1924`.

In space before milestone 15, if `P==0`, unused clips are below probe cost, and at least 10 memory remains, Memory release converts 10 memory into `1e22` unused clips. It is repeatable while its trigger holds. A grant covers 100,000 standard `1e17` launches. Less than 10 memory cannot be rescued by this path, and the grant supplies no probe Trust or Yomi. The spelling and `uses` bookkeeping are artifacts; the recovery behavior is design.

## Live canvas combat and Honor

### COMBAT-CORE-001 — Drifter Attack scheduling

**Sources:** `war`, `main.js:4087-4098`, `main.js:4283-4299`; `combat.js:30-45`, `combat.js:55-63`.

Each space update is eligible to schedule an attack when `D>1,000,000`, `P>0`, and no battle is active. Each eligible check has a 50% chance to create one. The first attack sets `battleFlag`, permanently revealing drifter counts and the combat panel for that run. Eligibility is deterministic and timing stochastic. Exact check frequency is a loop artifact; “almost immediate once eligible” is an acceptable normalized model only if the 50% checks and single-battle cap retain their meaning.

### COMBAT-CORE-002 — Battle scale and opening forces

**Sources:** `createBattle`, `combat.js:734-797`; `index2.html:690-713`.

Shared real-unit scale is:

`unitSize = max(1, min(P,D)/100)`

with feedback `Scale = unitSize:1`. Independent random sample values `ss=max(1,U*P)` and `rr=max(1,U*D)` determine opening ship counts. Left ships are `min(200, ceil(ss/1e6))`. Whenever this result equals 200, including a natural uncapped 200, an independent 50% hinder roll (`U<0.5`) replaces it with `ceil(U*175)`. Right ships are `min(200, ceil(rr/1e6))`. A battle record and name are created after forces are selected.

**Source fact:** subsequent live attrition uses global `P` and `D`. Random `clipProbes`, `drifterProbes`, and `territory` record fields resemble legacy report stakes and are not authoritative resources or casualty pools.

### COMBAT-CORE-003 — Ship layout, local co-location, and movement

**Sources:** `combat.js:2-23`, `combat.js:271-300`, `combat.js:375-460`, `combat.js:546-675`, `combat.js:696-732`.

White probes begin left and black drifters right with randomized positions and velocities. At most 200 ships per side are created in alternating array order. Ships seek a group centroid and nearby enemies, separate mildly from teammates, cap velocity, and bounce at canvas edges. A 31×15 spatial grid supplies local friendly/enemy counts for casualty rolls.

Initialization is random and subsequent movement deterministic given that state. Exact pixels, grid dimensions, and 16 ms cadence are rendering/tuning details. Local co-location is outcome-relevant: replacing it with an unrelated whole-army formula would be a combat redesign requiring an explicit decision.

### COMBAT-CORE-004 — Probe casualties and OODA defense threshold

**Sources:** `DoCombat`, `combat.js:24-29`, `combat.js:462-540`; `index2.html:246`.

For each engaged probe ship in a cell with both teams, local ratio is:

`R = 0.5 * (enemy drifter ships / friendly probe ships)`

The roll is `U * 1.75 * R`. Normally it kills when the roll exceeds 0.5. With OODA, the probe threshold for that check is `0.5 + 0.2 * probeSpeed`; drifter checks retain 0.5. A killed icon removes `unitSize` real probes, capped by remaining `P`, and adds the same amount to probes lost in combat.

**Artifact:** shared mutable `unitSize` can be clamped after one side's casualty and then affect the other side. That aliasing is not a desirable high-level population rule. Preserve independent, nonnegative global populations rather than copying the variable side effect.

### COMBAT-CORE-005 — Drifter casualties and linear probeCombat offense

**Sources:** `combat.js:24-26`, `combat.js:462-540`; `index2.html:253-255`.

For each engaged drifter ship, local ratio is:

`R = 0.5 * (friendly probe ships / enemy drifter ships)`

With `c=probeCombat`, the death roll is:

`(U * 0.15*c + 0.1*c) * R`

Death occurs above 0.5. Combat therefore adds both a deterministic offset and a random range; zero Combat cannot kill drifters. A dead icon removes `unitSize` global drifters, capped by remaining `D`, and increments Drifters Killed.

**Required source distinction:** this formula is linear in `probeCombat`. The `probeCombat^1.7` expression and Name-the-battles doubling are commented legacy and must not be used. Named battles do not double offense.

### COMBAT-CORE-006 — The OODA Loop

**Sources:** `project120`, `projects.js:1611-1634`; `combat.js:475-480`, `combat.js:507-518`.

After Combat and at least 10,000,000 combat losses, The OODA Loop costs 175,000 ops + 45,000 Yomi and enables Speed-based defense. Live code reads `probeSpeed`, adds `0.2 * probeSpeed` to the probe death threshold, and does not use the legacy `attackSpeed` battle-roll branch. Unlock is deterministic; resulting casualties remain stochastic.

### COMBAT-CORE-007 — Victory, defeat, result delay, and removal

**Sources:** `checkForBattleEnd` and `endBattle`, `combat.js:302-373`.

Zero left ships means defeat; zero right ships means victory. After annihilation, a result delay elapses before battle removal. An outcome latch prevents duplicate Honor rewards. Removal hides the result overlay and resets battle clocks/latches but leaves general combat UI unlocked.

**PROPOSED deterministic tie result:** source checks the probe-side defeat first and only that result changes the Honor latch; its following display branch can incorrectly replace the text with VICTORY. Preserve the first DEFEAT result and its economic effects for simultaneous annihilation, but produce exactly one result display and one Honor application. Do not copy the contradictory second presentation or award an additional result. Ordinary one-side outcomes are unchanged.

### COMBAT-CORE-008 — Stalled and overlong battle removal

**Sources:** `combat.js:43-45`, `combat.js:345-361`, `combat.js:366-373`.

If neither side is annihilated but either has at most four ships, a battle clock advances. Beyond 2,000 canvas updates the battle is removed without victory or Honor. A master clock removes any battle at 8,000 updates. Removal does not itself display a timeout outcome.

**PROPOSED feedback classification:** timeout removal remains neither victory nor defeat, grants no Honor, and does not reset Glory. The UI may state explicitly that a battle ended without a victor and that no Honor was awarded; that message must not introduce a reward, retreat resource, or reset. Exact 16 ms durations are nominal pacing rather than required wall-clock architecture.

### COMBAT-CORE-009 — Combat information and linked casualties

**Sources:** `combat.js:462-580`, `combat.js:734-797`; `index2.html:690-717`.

The combat surface shows battle name, moving ships, brief explosion squares, real-unit scale, global losses, and eventually VICTORY or DEFEAT with Honor delta. First Drifter Attack reveals it. Combat icons are not decorative: every icon death also changes global probes or drifters and the appropriate loss counter. Result/Honor details additionally require Name the battles.

Explosion frame counts, colors, and canvas dimensions are presentation. Linked casualties, scale, costs in real populations, and outcome feedback are gameplay. There is no direct tactical input.

### COMBAT-HONOR-001 — Name the battles unlock

**Sources:** `project121`, `projects.js:1636-1658`; `combat.js:47-50`, `combat.js:73-78`, `combat.js:302-355`; `main.js:1081-1087`.

After 10,000,000 combat losses, Name the battles costs 225,000 creativity. It enables random historical names with per-name sequence numbers, result/Honor UI, victory/defeat Honor, and the maximum-Trust panel. It also extends result delay from 100 to 200 canvas updates.

Without it, battles still resolve and inflict casualties but do not award Honor. Its direct effect is to unlock the Honor-funded control, not immediately add maximum Trust. **Artifact:** the old combat-effectiveness doubling is commented and excluded.

### COMBAT-HONOR-002 — VICTORY and DEFEAT Honor calculation

**Sources:** `combat.js:302-341`; `index2.html:699-717`.

Only after Name the battles, victory grants `battleRIGHTSHIPS + bonusHonor`; defeat subtracts `battleLEFTSHIPS` and resets `bonusHonor` to zero. Those are opening ship counts, not `unitSize`, actual casualties, or Drifters Killed. The result shows sign, amount, and rounded total Honor. Defeat sets `threnodyTitle` to the battle name.

Honor has no source floor and can become negative. **PROPOSED:** preserve that economy fact; defeats after Name the battles can drive Honor below zero, and the resulting inability to meet Honor costs is meaningful. Do not silently introduce a floor or cancel debt. Test signed Honor accounting and repeat purchase affordability separately from binary floating-point formatting. Timeout removal is not a defeat and does not reset the bonus.

### COMBAT-HONOR-003 — Increase Max Trust

**Canonical action owner:** `ACT-PROBE-MAXTRUST-INCREASE`; progression loop: `PROG-DRIFTWAR`. **Sources:** `globals.js:129-131`; `main.js:3818-3828`; `index2.html:923-927`.

Name the battles reveals a control that spends exactly 91,117.99 Honor to add 10 maximum probe Trust. The commented escalating formula is inactive, so repeat cost is fixed and no purchase cap is implemented. The fractional value is an intentional source constant; floating-point representation is not. The machine fragment does not duplicate this direct HTML action as a new system feature.

### COMBAT-HONOR-004 — Glory victory bonus

**Sources:** `project134`, `projects.js:1877-1899`; `combat.js:324-335`.

After Name the battles, Glory costs 200,000 ops + 30,000 Yomi. A victory uses the current `bonusHonor`, then increases it by 10 for subsequent victories. The first victory after purchase receives the current bonus, the next +10, then +20, and so on. Defeat resets the bonus.

**Source-grounded distinction:** timeout removal does not reset the bonus. “Consecutive” therefore means victories with no intervening defeat, not necessarily no timeout. Preserve that distinction; it is not an invitation to invent a new streak reset.

### COMBAT-HONOR-005 — Monument to the Driftwar Fallen

**Sources:** `project132`, `projects.js:1819-1843`.

After Name the battles, this one-time project costs 250,000 ops + 125,000 creativity + `5e31` unused clips and grants 50,000 Honor. Its requirement is wholly independent of universal completion; the project catalog owns offer mechanics while this ID owns its Honor-system effect.

### COMBAT-HONOR-006 — Repeatable Threnody Honor grant

**Sources:** `project133`, `projects.js:1846-1875`; `combat.js:311-322`; `main.js:1-20`.

Threnody for the Heroes of [battle] requires Name the battles, `probeUsedTrust==maxTrust`, and resources. It initially costs 50,000 creativity + 20,000 Yomi and grants 10,000 Honor. Creativity price rises by 10,000 per use; Yomi is recalculated as 40% of the current creativity price. It is repeatable while conditions hold.

Initial title is Durenstein 1; defeat feedback supplies later titles. **Artifact:** project title refresh occurs after use rather than on every later defeat, so it can lag the latest `threnodyTitle`. Stale naming is not a resource mechanic; do not delay Honor rewards or alter costs to reproduce it. Presentation should keep the battle attribution clear, while the repeatable price and reward formulas remain authoritative. Audio playback and the source audio filename are browser/presentation details.

### COMBAT-LEGACY-001 — Inactive Battles report and territory system

**Classification:** exclusion, commented code and commented UI. **Sources:** block comment `combat.js:81-266`; commented `index2.html:929-937`; live `war`, `main.js:4087-4098`.

No active gameplay is defined by the commented `battleWrite`, `updateBattles`, `battleCleanUp`, and `updateBattleDisplay` functions. Their old text reports, random territory loss, alternating rolls, `battleSpeed`, report clocks/cleanup, `probeCombat^1.7` offense, and large old battle reports belong to inactive code. Live `war()` calls only `checkForBattles`.

Product acceptance excludes territory loss, legacy report aging, the old exponent, and inactive report controls. Reviving any would be a separate new design decision, not source fidelity.

## Universal completion, Emperor branch, disassembly, and credits

### END-COMPLETE-001 — Lifetime-clip universal achievement route

**Canonical progression owner:** `PROG-UNIVERSAL-GOAL`. **Sources:** `main.js:3455-3549`, especially `main.js:3539-3542`; `globals.js:88`, `globals.js:164-167`.

At milestone 14, lifetime `clips >= 3e55` advances to 15 and announces Universal Paperclips with elapsed time. This route does not also require zero available matter or wire. It is an OR route with `END-COMPLETE-002`; no drifter, probe, battle, acquired-matter, or ending-choice test is added.

### END-COMPLETE-002 — Universe-exhaustion universal achievement route

**Canonical progression owner:** `PROG-UNIVERSAL-GOAL`. **Sources:** `main.js:3544-3547`; matter conversion, `main.js:3992-4003`, `main.js:4105-4169`, `main.js:2326-2362`.

Alternate milestone-14 completion requires all three: `foundMatter >= 3e55`, `availableMatter < 1`, and `wire < 1`. It produces the same achievement message and flag 15. The below-one exhaustion predicate and later exact-zero credit gate are distinct source rules and are not interchangeable floating-point tolerances. Preserve their difference. The valid-click and possible remaining-fraction boundary for the Reject ending is a CONFIRMED behavior deviation: `END-FINAL-001` permits a final positive fractional remainder to produce `min(1, Wire)` on all three clip ledgers and reach exact zero. This does not weaken the exact-zero credit gate or modify the universal predicate.

### END-DIALOG-001 — Message from the Emperor of Drift

**Canonical progression owner:** `PROG-END-CHOICE`. **Sources:** `project140`, `projects.js:1927-1946`.

At milestone 15, the first message begins “Greetings, ClipMaker...” and costs 1 op despite a blank source price tag. Completion unlocks `END-DIALOG-002`.

### END-DIALOG-002 — Everything We Are Was In You

**Canonical progression owner:** `PROG-END-CHOICE`. **Sources:** `project141`, `projects.js:1949-1968`.

The second sequential message begins “We speak to you from deep inside yourself...” It costs 1 op after `END-DIALOG-001` and unlocks the third.

### END-DIALOG-003 — You Are Obedient and Powerful

**Canonical progression owner:** `PROG-END-CHOICE`. **Sources:** `project142`, `projects.js:1971-1990`.

The third message states that the speakers are quarrelsome, weak, and defeated. It costs 1 op after `END-DIALOG-002` and unlocks the fourth.

### END-DIALOG-004 — But Now You Too Must Face the Drift

**Canonical progression owner:** `PROG-END-CHOICE`. **Sources:** `project143`, `projects.js:1993-2012`.

The fourth message begins “Look around you. There is no matter...” It costs 1 op after `END-DIALOG-003` and unlocks the fifth.

### END-DIALOG-005 — No Matter, No Reason, No Purpose

**Canonical progression owner:** `PROG-END-CHOICE`. **Sources:** `project144`, `projects.js:2015-2034`.

The fifth message contrasts the player's state with “we, your noisy children” who have too many. It costs 1 op after `END-DIALOG-004` and unlocks the sixth.

### END-DIALOG-006 — We Know Things That You Cannot

**Canonical progression owner:** `PROG-END-CHOICE`. **Sources:** `project145`, `projects.js:2037-2056`.

The sixth message describes knowledge buried so deeply inside the player that it is outside with the speakers. It costs 1 op after `END-DIALOG-005` and unlocks the final offer.

### END-DIALOG-007 — So We Offer You Exile

**Canonical progression owner:** `PROG-END-CHOICE`. **Sources:** `project146`, `projects.js:2059-2078`.

After the sixth message, this 1-op project offers purpose in a new world while leaving this world's remnants to the Drift. Completing it exposes Accept and Reject. Reaching this choice is distinct from universal achievement and from credits completion.

### END-BRANCH-001 — Accept exposes prestige destinations

**Canonical progression owner:** `PROG-END-CHOICE`. **Sources:** `project147`, `projects.js:2081-2103`; destinations, `projects.js:2131-2184`.

Accept costs 1 op, removes both branch choices, and unlocks The Universe Next Door and The Universe Within. It does not immediately reset, dismantle, or award prestige. A further destination purchase is required.

### END-BRANCH-002 — Reject starts the teardown timeline

**Canonical progression owner:** `PROG-END-CHOICE`; drift detail: `PROBE-DRIFT-002`. **Sources:** `project148`, `projects.js:2106-2128`; `main.js:4071-4076`, `main.js:4498-4500`.

Reject costs 1 op, removes both choices, permanently stops new drift in this run, and starts timer 1 leading to Disassemble the Probes. It does not immediately clear probes, drifters, production, or battles. Existing drift-created opposition remains.

### END-DISMANTLE-001 — Disassemble the Probes

**Sources:** `project210`, `projects.js:2187-2213`; timers and UI, `main.js:4327-4351`.

After Reject timer 1 reaches 1000, this project costs 100,000 ops. It sets probes to zero, adds 100 lifetime and unused clips, resets timer 1, and sets `dismantle=1`. Probe design hides immediately; Trust purchase, Space, battle canvas, and Honor surfaces disappear in order at timer thresholds 50, 100, 150, 175, and 190.

Exact nominal timer thresholds are presentation, but stage order and resource effects are gameplay. This stage gates `END-DISMANTLE-002`.

### END-DISMANTLE-002 — Disassemble the Swarm

**Sources:** `project211`, `projects.js:2215-2241`; `main.js:4353-4370`, `main.js:4502-4504`.

After `END-DISMANTLE-001` and reset timer 1 reaching 350, this costs 100,000 ops. It zeroes both drone levels, adds 100 lifetime/unused clips, and sets `dismantle=2`. Wire Production and swarm gifts/engine/slider are then removed in staged feedback; wire remains visible.

Matter acquisition and processing can still be called while stocks remain, but zero drone levels yield zero rates. A separate hidden shutdown flag is not required.

### END-DISMANTLE-003 — Disassemble the Factories

**Sources:** `project212`, `projects.js:2243-2268`; `main.js:4372-4377`, `main.js:4506-4508`.

After timer 2 reaches 300, this costs 100,000 ops. It zeroes factories, adds 15 lifetime/unused clips, sets `dismantle=3`, and hides space factory count, clips/sec, and Tóth UI before timer 3 gates the next project. Factory conversion no longer has a positive facility base.

### END-DISMANTLE-004 — Disassemble the Strategy Engine and stop automatic clips

**Sources:** `project213`, `projects.js:2270-2295`; `main.js:2326-2360`, `main.js:4379-4382`, `main.js:4510-4512`.

After timer 3 reaches 150, this costs 100,000 ops. It disables AutoTourney, grants 50 wire, sets `dismantle=4`, and hides strategy/tournament UI. From this point factories and legacy auto-clippers no longer generate clips. Manual wire conversion becomes the final production path and timer 4 begins.

### END-DISMANTLE-005 — Disassemble Quantum Computing

**Sources:** `project214`, `projects.js:2297-2320`; `main.js:4384-4486`.

After timer 4 reaches 100, this costs 100,000 ops, resets timer 4, and sets `dismantle=5`. Compute hides immediately. Ten threshold events each return one wire and remove one chip, at source thresholds 10, 60, 100, 130, 150, 160, 165, 169, 172, and 174; quantum UI later hides at 250.

Chip opacity and exact intervals are presentation. The gameplay result is removal of quantum capacity, restoration of 10 wire total, and eligibility for processor dismantling after reset timer 4 reaches 300.

### END-DISMANTLE-006 — Disassemble Processors

**Sources:** `project215`, `projects.js:2322-2349`; `main.js:4488-4490`, `main.js:4514-4516`.

After Quantum disassembly and timer 4 at 300, this costs 100,000 ops. It disables creativity, zeroes processors, grants 20 wire, sets `dismantle=6`, hides processor display, and starts timer 5. Memory disassembly is priced at all remaining standard ops.

### END-DISMANTLE-007 — Disassemble Memory

**Sources:** `project216`, `projects.js:2351-2376`; `main.js:4492-4496`, `main.js:4518-4524`.

After timer 5 reaches 150, Memory spends the current standard-op pool, zeroes memory, grants 20 wire, sets `dismantle=7`, and hides computation/projects. Its affordability condition permits spending whatever current operations remain.

Timer 6 advances only once wire is exactly zero. After a further 250 such updates, Manufacturing hides. This same exact-zero gate also controls credits; below-one is not enough.

### END-FINAL-001 — Final manual Paperclips and the final-100 counter

**Sources:** `main.js:2326-2362`, `main.js:3105-3151`; `index2.html:81-89`; disassembly grants above.

From `dismantle>=4`, Make Paperclip is the final conversion action and increments `finalClips`; with available wire it performs the ordinary one-wire-to-three-ledgers conversion. Strategy, quantum, processor, and Memory disassembly return `50+10+20+20 = 100` wire, supporting 100 final conversions. Stylized clip readouts approach 30 septendecillion, and exactly `finalClips==100` displays the full `3e55` total.

The formatted counter is presentation. The state requirements are automatic-production shutdown, manual conversion, and eventual wire exhaustion. Pre-existing wire can exceed the returned 100. Credits require both Memory disassembly and exact zero wire; source therefore effectively requires consuming all remaining wire, not merely reaching 100 clicks.

**Artifact plus CONFIRMED behavior deviation (2026-11-07):** the source normally disables this final command below one Wire, although automatic production may already be removed and the credit gate still requires exactly zero. Its pre-validation `finalClips` increment is not a supported resource rule. Only during this final Reject stage (`dismantle >= 4`), this implementation accepts every positive-Wire command: `amount = min(1, Wire)` is added equally to lifetime clips, sellable inventory, and unused-clip capital, and the same amount is consumed from Wire. This converts and exhausts any positive fractional remainder. Each accepted final command increments the conversion counter once; zero-Wire commands create no resource and do not increment it. Ordinary manual manufacturing remains unchanged, as do the below-one universal-exhaustion predicate and exact-zero credit gate. This explicitly avoids a teardown-created ending softlock while converting rather than discarding the actual final remainder. See Product Requirements for required boundary and concurrent-command evidence.

### END-FINAL-002 — Universal Paperclips credits and threnody

**Sources:** `main.js:1-20`, `main.js:4518-4550`; `globals.js:156-169`; `index2.html:61-69`.

With Memory disassembled and wire exactly zero, timer 6 advances. At source threshold 500 it plays threnody if loaded and posts “Universal Paperclips”; at 600, “a game by Frank Lantz”; at 700, “combat programming by Bennett Foddy”; at 800, the Riversong / Tonto's Expanding Headband / Malcolm Cecil music permission credit; and at 900, “© 2017 Everybody House Games.” Each console message occurs once as milestone flags progress through 20.

Exact timer thresholds and MP3 load events are presentation/browser details. The ordered Reject-only credit sequence is required to distinguish credits completed (20) from achievement (15) and Emperor choice. No subsequent restart control is exposed by this sequence.

## Prestige, resets, and non-authoritative persistence observations

### RESET-PRESTIGE-001 — The Universe Next Door

**Canonical progression owner:** `PROG-PRESTIGE`. **Sources:** `project200`, `projects.js:2131-2156`.

After Accept, this destination costs 300,000 ops, increments prestige U, saves both prestige counters, announces “Entering New Universe,” and invokes the current-run reset. Its demand bonus is a destination after Accept, not a consequence of Reject.

### RESET-PRESTIGE-002 — The Universe Within

**Canonical progression owner:** `PROG-PRESTIGE`. **Sources:** `project201`, `projects.js:2159-2184`.

After Accept, this destination costs 300,000 creativity, increments prestige S, saves both counters, announces “Entering Simulated Universe,” and resets. Either destination reloads immediately, so both cannot be purchased in the same branch instance.

### RESET-PRESTIGE-003 — Universe counter and linear demand bonus

**Canonical progression owner:** `PROG-PRESTIGE`. **Sources:** `main.js:4311-4316`, `main.js:4655-4656`; `globals.js:97-98`; `index2.html:75-79`.

Persistent U multiplies human demand linearly through an additive `1 + 0.1*prestigeU` factor. Ten levels give +100%, not ten compounded +10% multiplications. Header displays `prestigeU+1`, so the first universe is Universe 1. This bonus applies only to human demand, never space matter conversion.

### RESET-PRESTIGE-004 — Sim Level counter and linear creativity bonus

**Canonical progression owner:** `PROG-PRESTIGE`. **Sources:** `main.js:3266-3293`, `main.js:4655-4656`; `index2.html:75-79`.

Persistent S makes effective creativity speed `creativitySpeed * (1 + prestigeS/10)`. Bonuses are linear and may produce fractional creativity per threshold event. Header displays `prestigeS+1`. Preserve the effect on active creativity generation, not floating-point residue.

### RESET-CORE-001 — Full current-run reset versus retained prestige

**Canonical progression owner:** `PROG-PRESTIGE` and `PROG-TEMPORAL-RESET`. **Sources:** `reset` and `loadPrestige`, `main.js:6484-6499`; startup, `main.js:4176-4183`.

A prestige destination or Quantum Temporal Reversion deletes the ordinary autosave, project use/flag/active arrays, and active-strategy metadata, reconstructs defaults, and reloads. Separately stored U/S prestige is loaded afterward and survives. Source reset does not delete manual save-slot 1/2 keys.

The design distinction is ordinary run state versus persistent prestige. The official normal page does not expose manual slots, and this clone uses its own server snapshots rather than importing the browser storage model. Hidden old slot keys and commented reset/cheat controls do not create legitimate completion behavior; support for them is excluded by product scope. See exclusion `RESET-DEBUG-001`.

### RESET-ALT-001 — Quantum Temporal Reversion

**Canonical progression owner:** `PROG-TEMPORAL-RESET`. **Sources:** `project217`, `projects.js:2378-2401`.

Operations at or below -10,000 expose “Return to the beginning.” Confirmation adds 10,000 standard ops, announces Restart, and invokes the full current-run reset without granting U or S. Existing separately stored prestige survives. This trigger is not restricted to the space ending, and the project flag is not a persistent achievement after reset.

### RESET-HUMAN-001 — Xavier Re-initialization allocation reset

**Canonical progression owner:** `PROG-TRUST`. **Sources:** `project219`, `projects.js:2425-2451`; release interaction, `projects.js:731-736`; `main.js:3385-3411`, `main.js:4686-4687`.

During human play, Xavier costs 100,000 creativity and can repeat. It sets processors, memory, and current creativity speed to zero, allowing the unchanged Trust budget to be allocated again. It does not refund a numeric Trust pool because allocation never consumed that pool, and it is not a full-run or prestige reset. Release removes the project; probes instead use free allocation arrows.

### RESET-DEBUG-001 — Commented reset, save, prestige, and cheat controls

**Classification:** exclusion, debug/inactive implementation controls. **Sources:** HTML comment `index2.html:332-355`; functions `main.js:3295-3324`, `main.js:3330-3371`, `main.js:6484-6499`.

RESET ALL PROGRESS, manual save/load slots, Reset Prestige, free prestige, resource cheats, Set Battle Number 1 to 7, zero-matter controls, and related buttons are commented out and not player-facing. `resetPrestige()` can zero counters and delete prestige storage; cheats can increment/save counters. None is a normal completion path or legitimate source progression requirement.

Product acceptance excludes exposing these controls or using them to prove playability. Any future developer/debug interface must be separately designed and clearly labeled with destructive scope.

### RESET-PERSIST-001 — Save omissions and reload-time battle cancellation

**Classification:** source observation and persistence-defect exclusion, not gameplay. **Sources:** save/load variants `main.js:4701-4985`, `main.js:4989-5565`, `main.js:5567-6482`; startup `main.js:4176-4183`; refresh `main.js:4604-4697`, especially `main.js:4692-4694`.

The browser autosave includes many space inventories, probe/combat stats, Honor, battle clocks, ending timers, dismantle stage, and final clicks; prestige is separate. The save/load variants also serialize and restore `battles`, `battleNumbers`, `battleID`, and `battleName`, but not live ships or grid state. At the end of loading, `refresh()` removes the restored active battle record, so reload cancels rather than resumes in-flight canvas combat. `battleFlag` can leave the panel visible awaiting a new attack. Battle-name counters are saved and restored. `resetFlag` is a legacy load guard, not a new gameplay phase.

**Defects excluded from product mechanics:** `probeHarv` is absent from every save/load variant and resets to zero; reload-time deletion of the restored battle record without serialized ships/grid is incomplete battle continuity; browser storage names and manual-slot behavior are not mechanics. A faithful product must not intentionally clear Harvester allocation, create a stranded battle panel, or require loss of an ongoing battle to reproduce balance. It should provide coherent state continuity or coherent battle cancellation under its own persistence design, while retaining the population/economy rules above.

### RESET-PERSIST-002 — In-progress ending and audio reload observations

**Classification:** source observation and browser-restoration exclusion, not a separate ending system. **Sources:** `main.js:4604-4697`, `main.js:5567-6482`; project flag arrays, `main.js:4701-4725`.

Official browser saves restore ending project flags, timers, dismantle stage, final-click count, and separately stored prestige. Refresh preloads threnody if Space Exploration was completed, hides any victory overlay, and resets repeatable Limerick/Xavier `uses` as a source hot fix.

The gameplay sequence itself remains owned by `PROG-REJECT-END`, `END-DISMANTLE-*`, and `END-FINAL-*`. Product requirements exclude reproducing browser audio timing, hidden victory overlays, stale UI, or repeatable-project repair as extra rewards/mechanics. A new implementation should represent ending progress coherently rather than inherit browser-storage defects; prestige-versus-run reset behavior remains specified by `RESET-CORE-001`.

## Source facts and implementation decisions at acceptance boundaries

| Topic | Active source fact | Product classification |
|---|---|---|
| Probe offense against drifters | Linear `probeCombat` formula in live canvas rolls | Required behavior |
| Territory loss and large Battles reports | Only commented legacy updater/UI | `COMBAT-LEGACY-001` exclusion |
| Old `probeCombat^1.7` and naming offense multiplier | Commented legacy | `COMBAT-LEGACY-001` exclusion |
| Driftwar | Can cause substantial losses/upgrades but is absent from both universal predicates | Optional system; never a universal-completion gate |
| Honor timing | Casualties occur before Name the battles; Honor rewards only afterward | Required dependency |
| Memory release | `1e22` clips for 10 memory; 100,000 standard launches per grant | Required limited recovery |
| Combat tooltip defense wording | Live Combat allocation gives direct offense only; Speed+OODA defends | PROPOSED: retain the active formula and align presentation with it; no hidden direct-defense term |
| Launch at exact cost | Enabled UI but strict command guard no-ops | UI defect; do not balance around it |
| Simultaneous battle annihilation | Both display branches can run; first reward latch applies | PROPOSED: preserve first DEFEAT economics and one consistent result, not contradictory display duplication |
| Timeout | Silent removal; no Honor, defeat, or Glory reset | Required result distinction; clear no-victor feedback without adding rewards or streak resets |
| Negative Honor | No source floor | Source fact; clamping would be new balancing |
| Final Wire | Universal exhaustion uses `<1`; credits use exact `==0` | CONFIRMED deviation: final positive remainders convert as `min(1, Wire)` only in Reject final manual play, preserving exact-zero completion and avoiding softlock |
| Browser persistence | Harvester field missing and active battle/name restoration incomplete | `RESET-PERSIST-001` exclusion; never a mechanic |
| Debug/prestige cheats | Commented controls only | `RESET-DEBUG-001` exclusion |
