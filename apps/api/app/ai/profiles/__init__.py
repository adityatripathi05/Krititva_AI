"""AI role profiles (LLD §5.1). Each agent is data: retrieval policy + prompts +
output schema + draft persistence. Core profiles register via the
``krititva.agents`` entry-point group; core code never imports them by path."""
