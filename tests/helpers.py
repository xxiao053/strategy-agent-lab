def exit_facts(stop=92,target=150):
    return dict(candidate_id='offline-fixture',stop=stop,target=target,volatility_unit=2)


def bound_reply(ctx,verdict='fail'):
    return {'assessments':[dict(candidate_id=c['candidate_id'],verdict=verdict,
        checks=[dict(name=n,verdict=verdict,reason='Offline fixture, not real model judgment',
                     start_date=c['handle_start'] if n=='handle' else c['left_rim'],
                     end_date=c['right_rim'] if n=='cup' else c['handle_end']) for n in ['cup','handle','coherence']],
        evidence='Offline fixture, not real model judgment',missing_information=[]) for c in ctx['candidates']]}
