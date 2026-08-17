# Separate course architecture drafts from formal courses

Course architecture drafts are stored as an independent aggregate instead of reusing `Course` and `KnowledgePoint`. This keeps model-produced, incomplete, stale, or user-edited candidates outside the formal learning structure until deterministic validation and explicit publication succeed, at the cost of a deliberate mapping step during publication.
