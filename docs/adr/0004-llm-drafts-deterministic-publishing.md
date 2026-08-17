# Let the LLM propose drafts and let deterministic services publish

The LLM may only return schema-validated course candidates that cite an allowed real chunk. A deterministic publishing service revalidates the draft and writes every formal entity in one user-confirmed transaction; this preserves traceability and rollback guarantees even though it prevents the model from directly creating courses.
