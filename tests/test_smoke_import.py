def test_import_current_tree():
    import agent.graph
    import analysis.memory
    import analysis.report
    import executors
    import safety.sandbox
    import server.main
    import viz.chart

    executors.init_executors()
    agent.graph.build_graph()
    assert set(executors.registry.list_executors()) >= {"pandas", "sql"}
