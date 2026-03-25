import sys, re
sys.stdout.reconfigure(encoding='utf-8')

checks = []

def read(f):
    return open(f, encoding='utf-8', errors='replace').read()

# flow.py
c = read('core/tool_evolution/flow.py')
checks.append(('flow: chunk on first attempt for large tools',   'tool_size > OVERFLOW_SIZE_BYTES' in c and '_chunk_evolve' in c))
checks.append(('flow: EvolutionConstraintMemory imported',       'EvolutionConstraintMemory' in c))
checks.append(('flow: EvolutionFailureClassifier imported',      'EvolutionFailureClassifier' in c))
checks.append(('flow: constraint block injected into analysis',  "analysis['constraint_block']" in c))
checks.append(('flow: record_failure called on retry',           'record_failure' in c))
checks.append(('flow: DEP_BLOCKED exits early',                  'DEP_BLOCKED' in c))
checks.append(('flow: target_functions passed to sandbox',       'target_functions=proposal.get' in c))
checks.append(('flow: per-model confidence threshold',           '_min_confidence = 0.35 if _provider' in c))
checks.append(('flow: 3 retry attempts',                         'for attempt in range(3)' in c))
checks.append(('flow: _chunk_evolve method defined',             'def _chunk_evolve' in c))

# analyzer.py
c = read('core/tool_evolution/analyzer.py')
checks.append(('analyzer: exact-case experimental path first',   "tools/experimental/{tool_name}.py" in c))
checks.append(('analyzer: case-insensitive scan fallback',       'glob' in c or 'lower()' in c))

# code_generator.py
c = read('core/tool_evolution/code_generator.py')
checks.append(('codegen: already_improved accumulator',          'already_improved: List' in c))
checks.append(('codegen: already_implemented passed forward',    'already_implemented=already_improved' in c))
checks.append(('codegen: op_spec fallback from handler source',  '_extract_handler_parameters(handler_code' in c))
checks.append(('codegen: _build_context_window used',           '_build_context_window' in c))
checks.append(('codegen: constraint_block in improve_handler',   "proposal.get('constraint_block')" in c))
checks.append(('codegen: _check_missing_return used',           '_check_missing_return' in c))
checks.append(('codegen: _invalid_service_calls used',          '_invalid_service_calls' in c))
checks.append(('codegen: dead AST block removed',               "svc = func.value.attr  # 'services'" not in c))

# proposal_generator.py
c = read('core/tool_evolution/proposal_generator.py')
checks.append(('proposal: constraint_section in prompt',         'constraint_section' in c))
checks.append(('proposal: duplicate proposal guard',             '_is_duplicate_proposal' in c))
checks.append(('proposal: blocked libs note',                    'visualization' in c or 'graphviz' in c))
checks.append(('proposal: _record_proposal called',             '_record_proposal' in c))

# validator.py
c = read('core/tool_evolution/validator.py')
checks.append(('validator: duplicate capability check',          '_check_duplicate_capabilities' in c))
checks.append(('validator: syntax check present',                'ast.parse(improved_code)' in c))

# enhanced_code_validator.py
c = read('core/enhanced_code_validator.py')
checks.append(('enhanced: bare undefined call check wired',      '_check_bare_undefined_calls' in c))
checks.append(('enhanced: dangerous calls blocked',              '_DANGEROUS_CALLS' in c))

# sandbox_runner.py
c = read('core/tool_evolution/sandbox_runner.py')
checks.append(('sandbox: target_functions param',                'target_functions' in c))
checks.append(('sandbox: returned None skip for non-targeted',   'returned none' in c.lower()))
checks.append(('sandbox: rate-limit false positive skipped',     'rate-limit signals' in c))

# dependency_checker.py
c = read('core/dependency_checker.py')
checks.append(('depchecker: BLOCKED_LIBRARIES defined',          'BLOCKED_LIBRARIES' in c))
checks.append(('depchecker: pandas in blocked',                  "'pandas'" in c))
checks.append(('depchecker: blocked checked in _check_libraries','BLOCKED_LIBRARIES' in c and 'missing.append' in c))

# auto_evolution_orchestrator.py
c = read('core/auto_evolution_orchestrator.py')
checks.append(('auto_evo: disabled tools skipped',               'DISABLED_TOOLS' in c))
checks.append(('auto_evo: 6h cooldown',                          'COOLDOWN_HOURS = 6' in c))
checks.append(('auto_evo: misleading test score log removed',    'Evolution test score' not in c))

# pending_evolutions_manager.py
c = read('core/pending_evolutions_manager.py')
checks.append(('pending_mgr: health_after baseline fallback',    'health_before' in c and 'health_after' in c))
checks.append(('pending_mgr: health_after or fallback pattern',  '(report.health_score if report else None) or evolution.get' in c))

# tool_services.py
c = read('core/tool_services.py')
checks.append(('tool_services: storage.get returns None',        'FileNotFoundError' in c and 'return None' in c))

# evolution_constraint_memory.py
c = read('core/evolution_constraint_memory.py')
checks.append(('constraint_memory: DDL creates table',           'evolution_constraints' in c))
checks.append(('constraint_memory: record_failure',              'def record_failure' in c))
checks.append(('constraint_memory: build_constraint_block',      'def build_constraint_block' in c))
checks.append(('constraint_memory: upsert on conflict',         'ON CONFLICT' in c))

# failure_classifier.py
c = read('core/tool_evolution/failure_classifier.py')
checks.append(('classifier: OVERFLOW type',                      'OVERFLOW' in c))
checks.append(('classifier: DEP_BLOCKED type',                   'DEP_BLOCKED' in c))
checks.append(('classifier: PATTERN_LOOP type',                  'PATTERN_LOOP' in c))
checks.append(('classifier: INFRA type',                         'INFRA' in c))
checks.append(('classifier: seen_before checks cua.db',          'evolution_constraints' in c))
checks.append(('classifier: OVERFLOW_SIZE_BYTES exported',       'OVERFLOW_SIZE_BYTES' in c))

# --- Print results ---
passed = sum(1 for _, v in checks if v)
failed = [(n, v) for n, v in checks if not v]

print(f'\nAUDIT RESULTS: {passed}/{len(checks)} passed\n')
if failed:
    print('FAILED:')
    for name, _ in failed:
        print(f'  FAIL  {name}')
else:
    print('All checks passed.')
