"""Each YAML occurrence of an agent owns its step settings."""

import pytest

from praisonaiagents.agent.agent import Agent
from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser
from praisonaiagents.workflows.workflows import _step_agents


def parse(steps):
    return YAMLWorkflowParser().parse_string('''
name: reuse
agents:
  writer: {role: Writer, goal: Write, instructions: Write}
steps:
''' + steps)


def test_reused_agent_executes_distinct_actions_and_variables(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PRAISONAI_HOME', str(tmp_path))
    calls = []
    def chat(self, prompt, **kwargs):
        calls.append(prompt)
        return 'first-result' if len(calls) == 1 else 'second-result'
    monkeypatch.setattr(Agent, 'chat', chat)
    wf = parse('''
  - agent: writer
    name: outline
    action: "outline {{input}}"
    output_variable: draft
    max_retries: 1
  - agent: writer
    name: polish
    action: "polish {{previous_output}}"
''')
    first, second = (wf._normalize_single_step(s, i) for i, s in enumerate(wf.steps))
    assert (first.name, first.action, first.output_variable, first.max_retries) == ('outline', 'outline {{input}}', 'draft', 1)
    assert (second.name, second.output_variable, second.max_retries) == ('polish', None, 3)
    result = wf.start('topic')
    assert result['status'] == 'completed'
    assert calls == ['outline topic', 'polish first-result']
    assert result['variables']['draft'] == 'first-result'


@pytest.mark.parametrize('pattern', ['parallel', 'loop', 'repeat', 'if'])
def test_nested_occurrences_keep_their_own_action(pattern):
    nested = {
        'parallel': '  - parallel:\n      - {agent: writer, action: nested}\n',
        'loop': '  - loop: {over: items}\n    agent: writer\n    action: nested\n',
        'repeat': '  - repeat: {max_iterations: 1}\n    agent: writer\n    action: nested\n',
        'if': '  - if: {condition: "true", then: [{agent: writer, action: nested}]}\n',
    }[pattern]
    wf = parse('  - {agent: writer, name: original, action: original}\n' + nested)
    first = wf._normalize_single_step(wf.steps[0], 0)
    pattern_step = wf.steps[1]
    child = {'parallel': lambda: pattern_step.steps[0], 'loop': lambda: pattern_step.step,
             'repeat': lambda: pattern_step.step, 'if': lambda: pattern_step.then_steps[0]}[pattern]()
    second = wf._normalize_single_step(child, 0)
    assert first.action == 'original'
    assert second.action == 'nested'


@pytest.mark.parametrize('pattern', ['parallel', 'loop', 'repeat'])
def test_nested_occurrences_execute_with_their_own_action(pattern, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PRAISONAI_HOME', str(tmp_path))
    calls = []
    def chat(self, prompt, **kwargs):
        calls.append(prompt)
        return 'done'
    monkeypatch.setattr(Agent, 'chat', chat)
    nested = {
        'parallel': '  - parallel:\n      - {agent: writer, action: nested}\n',
        'loop': '  - loop: {over: items}\n    agent: writer\n    action: nested\n',
        'repeat': '  - repeat: {max_iterations: 1}\n    agent: writer\n    action: nested\n',
    }[pattern]
    wf = parse('  - {agent: writer, name: original, action: original}\n' + nested)
    wf.variables['items'] = ['one']
    result = wf.start('topic')
    assert result['status'] == 'completed'
    assert calls == ['original', 'nested\n\nContext from previous step:\ndone']


def test_loop_output_variable_belongs_to_loop_not_inner_task():
    wf = parse('  - loop: {over: items}\n    agent: writer\n    action: nested\n    output_variable: collected\n')
    pattern = wf.steps[0]
    assert pattern.output_variable == 'collected'
    assert wf._normalize_single_step(pattern.step, 0).output_variable is None


def test_parallel_reused_agent_is_visible_to_history_isolation():
    wf = parse('''
  - parallel:
      - {agent: writer, action: first}
      - {agent: writer, action: second}
''')
    first, second = wf.steps[0].steps
    assert _step_agents(first) == [first.agent]
    assert _step_agents(second) == [first.agent]


def test_yaml_graph_keeps_step_names_and_agent_assignment():
    wf = parse('  - {agent: writer, name: draft, action: draft}\n'
               '  - {agent: writer, name: polish, action: polish}\n')
    graph = wf.to_graph()
    assigned = {(e['source'], e['target']) for e in graph['edges'] if e['kind'] == 'assigned'}
    assert assigned == {('step:draft', 'agent:writer'), ('step:polish', 'agent:writer')}


@pytest.mark.parametrize('choice,expected', [('true', 'then-action'), ('false', 'else-action')])
def test_conditional_executes_selected_reused_agent(choice, expected, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(Agent, 'chat', lambda self, prompt, **kwargs: calls.append(prompt) or 'done')
    wf = parse('''
  - {agent: writer, action: before}
  - if:
      condition: "%s"
      then: [{agent: writer, action: then-action}]
      else: [{agent: writer, action: else-action}]
''' % choice)
    assert wf.start('topic')['status'] == 'completed'
    assert calls[0] == 'before'
    assert calls[1].startswith(expected)


def test_route_executes_reused_agent_without_stale_action(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = []
    def chat(self, prompt, **kwargs):
        calls.append(prompt)
        return 'chosen' if len(calls) == 1 else 'done'
    monkeypatch.setattr(Agent, 'chat', chat)
    wf = parse('''
  - {agent: writer, action: choose}
  - route: {chosen: writer}
''')
    assert isinstance(wf.steps[1].routes['chosen'][0], Agent)
    assert wf.steps[1].routes['chosen'][0] is wf.steps[0].agent
    assert wf.start('topic')['status'] == 'completed'
    assert calls[0] == 'choose'
    assert calls[1].startswith('topic')


def test_reused_audio_agent_dispatches_each_action(monkeypatch, tmp_path):
    from praisonaiagents.agent.audio_agent import AudioAgent
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(AudioAgent, 'speech', lambda self, *a, **kw: calls.append('speech') or 'audio')
    monkeypatch.setattr(AudioAgent, 'transcribe', lambda self, *a, **kw: calls.append('transcribe') or 'text')
    wf = YAMLWorkflowParser().parse_string('''
name: audio-reuse
agents:
  speaker: {agent: AudioAgent, role: Speaker, goal: Speak, llm: openai/tts-1}
steps:
  - {agent: speaker, name: speak, action: speech}
  - {agent: speaker, name: listen, action: transcribe}
''')
    assert wf.start('topic')['status'] == 'completed'
    assert calls == ['speech', 'transcribe']
