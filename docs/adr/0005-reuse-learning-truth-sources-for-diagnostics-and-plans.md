# Reuse learning truth sources for diagnostics and plans

V10 keeps questions and answers in the existing learning-activity and quiz-attempt model, routes diagnostic evidence through the existing mastery lifecycle, and treats `DailyTask` as the only execution truth source for study plans. Diagnostic and plan tables therefore record traceability, baselines, planning, and immutable versions instead of introducing parallel question, mastery, review, or task systems; this preserves existing lifecycle behavior and prevents completion state from drifting between two owners.
