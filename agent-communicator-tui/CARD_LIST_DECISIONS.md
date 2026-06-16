# CardList/ListState decisions

Phase 5 evaluated row-based tabs for shared CardList/ListState adoption while preserving custom DESIGN.md row/card renderers.

| Area | Decision | Rationale |
| --- | --- | --- |
| Agent switcher | Defer | Agent rows include group headers, hidden separators, unread states, and line-range scrolling by rendered height. Keep custom offset/scroll logic until a richer grouped CardList exists. |
| Memory records | Adopt shared ListState now | Memory rows are uniform records with selected index, offset, visible row count, and custom row rendering already isolated in `memoryRowLines`; selection/offset logic maps cleanly to `CardListState`. |
| Task chains/tasks | Defer | Tasks has two modes (chain list and focused task buckets), bucket headers, current/selected row variants, confirmations, forms, and agent filtering. A shared list state may help later but needs bucket-aware state. |
| Saved messages | Keep custom | Saved tab selection is a small wrapping agent grouping over saved records, not a scrollable card list today; custom logic is simpler and preserves behavior. |
| Swarm rows | Keep custom for now | Swarm sidebar combines swarm selection, main/member details, timeline loading, warning states, and custom cards; state is domain-specific and not worth migrating in this phase. |

Adopted abstraction: `CardListState` provides reusable selected/offset/count/visible movement and scroll-into-view behavior. It intentionally does not render rows, so domain-specific card rendering remains custom.
