---
intent: [validate]
task_type: [analyze]
domain: [technical]
primary_stage: verify
complexity_level: 2
source: public
Original Link: ""
Notes: "Part of the public showcase collection"
---

Perform a thorough code review of the following pull request for the **{{project_name}}** project.

PR title: {{pr_title}}
Language/framework: {{language_and_framework}}
PR description: {{pr_description}}
Code diff or key files: {{code_to_review}}

Review against this checklist and provide feedback on each category:

1. **Correctness** — Does the code do what the PR claims? Are there logic errors, off-by-one mistakes, or unhandled edge cases?
2. **Security** — Are there injection risks, hardcoded secrets, missing input validation, or improper auth checks?
3. **Performance** — Are there N+1 queries, unnecessary loops, missing indexes, or memory leaks?
4. **Readability** — Are variable names clear? Is the code self-documenting? Are complex sections commented?
5. **Testing** — Are there adequate unit tests? Are edge cases tested? Is test coverage sufficient for the changed code?
6. **Error Handling** — Are exceptions caught appropriately? Are error messages helpful? Are failures graceful?
7. **Architecture** — Does this fit the existing patterns? Is there unnecessary coupling? Would this be hard to change later?
8. **Style** — Does it follow the project's conventions and linting rules?

For each issue found, provide:
- File and line reference
- Severity: Blocker / Suggestion / Nit
- The problem
- A suggested fix (with code snippet if applicable)

Output as a structured review with a summary verdict: Approve / Request Changes / Needs Discussion.
