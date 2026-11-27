# Procedure: Lookup / List Pit Crew

Read-only. No confirmation required.

## Resolving a single pit crew member
Match on name. If multiple share a name, list matches and ask which one.

## Listing pit crew
- "Who's my plumber?" -> list_pit_crew(primary_trade="plumber") — the
  primary lookup maintenance-crud uses when suggesting an assignment.
- "Show me all my pit crew" -> list_pit_crew().
- Soft-deleted contractors aren't retrievable through list — only by
  known id.

## Trade matching for assignment
When called from maintenance-crud to suggest an assignment, match the
categorized problem against trade first. If no active contractor has
that trade (or only 'other' matches exist), say so plainly and ask who
to assign — don't guess.
