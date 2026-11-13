"""Central intelligence engine: providers, safety, retrieval, memory, tools, agents and the orchestrator.

Dependency direction (top depends on bottom, never the reverse):

    orchestrator  ->  agents (specs + runtime)  ->  tools  ->  retrieval / memory / safety  ->  providers
"""
