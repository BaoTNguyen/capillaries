<!-- arteries:start -->
## Arteries Memory

At session start, run `ARTERIES_CLI=codex bash .arteries/hooks/activate.sh` to start a new arteries run and load context.
On each user prompt, run `ARTERIES_CLI=codex bash .arteries/hooks/generic-observe.sh "<prompt>"` and use any returned text as additional context.

Arteries observes turns, builds memory, and may surface retrieved prompts.
<!-- arteries:end -->
