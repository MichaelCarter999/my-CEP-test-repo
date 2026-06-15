# Nautobot vs NetBox — the verdict for this project

**Short answer: Nautobot wins *for this CEP project*. For a pure DCIM/IPAM
deployment with no automation ambitions, NetBox is the better default.** They
share ancestry (Nautobot was forked from NetBox), so the data model feels almost
identical — the divergence is in everything around the model.

## Why Nautobot wins here

1. **Native, first-class GraphQL.** The CEP engine needs the *enriched* topology —
   devices plus the upstream-dependency relationship plus interface/cable context —
   in one query. Nautobot's GraphQL returns exactly that shape in a single round
   trip. NetBox has GraphQL too, but Nautobot's is more central to how the product
   expects to be consumed.

2. **Custom Relationships as a modelling primitive.** The "device X depends on
   device Y for reachability" edge — the heart of root-cause analysis — is a
   native Nautobot **Relationship** object (`upstream-dependency`). It's queryable,
   typed, and admin-editable. In NetBox you'd lean on cables + custom fields or a
   plugin to express the same dependency cleanly.

3. **The automation-platform narrative.** Nautobot Jobs, Git data sources, and the
   plugin/app framework let the *same platform* drive validation, seeding, and even
   simulation. That story — "your source of truth also runs your automation" — is
   exactly the pitch a Solutions Architect is making when arguing against a
   monolithic FM platform. It reinforces the demo's thesis.

4. **Git Data Source sync.** Topology/intended-state lives in Git and syncs into
   Nautobot — aligns with the "rules and topology are version-controlled" argument
   the sales pitch makes.

## Where NetBox would win

- **Smaller, faster footprint.** NetBox is lighter to stand up and run; for a
  laptop demo that's a real, fair point in its favour.
- **Larger plugin ecosystem and community gravity.** If you need an off-the-shelf
  integration, NetBox more often has one.
- **Pure DCIM/IPAM.** If you're *only* documenting racks, cables and addresses with
  no automation layer, NetBox's focus is an advantage, not a limitation.
- **Familiarity.** If the team already runs NetBox, the switching cost outweighs
  the marginal modelling benefit for a demo.

## How the repo hedges

The loader (`nautobot/populate_nautobot.py`) reads the vendor-neutral
`topology.json` and the CEP engine consumes a plain dependency list. A NetBox
port is a thin adapter swap — re-implement the loader against the NetBox API and
expose the same dependency edges. Nothing in the correlation engine is
Nautobot-specific. So the verdict is "Nautobot for this project's automation
story", not "you are locked into Nautobot".

## Bottom line

| If your goal is… | Pick |
|---|---|
| Source of truth that also drives automation + RCA dependency modelling | **Nautobot** |
| Lean, focused DCIM/IPAM documentation | **NetBox** |
| You already run one of them | The one you run |

For demonstrating topology-aware correlation as an automation capability —
which is this project — **Nautobot is the right call.**
