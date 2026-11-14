"""Attributed teaching cards, not a labeled market dataset or investment evidence."""
from copy import deepcopy

STOCKCHARTS='https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/cup-with-handle'
FIDELITY='https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/cup-with-handle'

PACK = {
    'version':'cup-teaching-v1',
    'limitations':'Published examples are retrospective teaching, not point-in-time test labels. '
                  'Schematics are project-made illustrations, never actual stock histories. '
                  'No future prices from the current research run are provided. Source rules do not silently replace the approved numeric contract.',
    'cases':[
        dict(id='published-classic',label='positive',source_url=STOCKCHARTS,
             provenance='Paraphrase of the publisher’s classic cup-and-handle teaching chart, not copied chart pixels.',
             lesson='A bowl-shaped consolidation recovers to an upper rim, followed by a smaller attached pullback and breakout. Judge that connected region, not the overall direction of the entire history.'),
        dict(id='published-emc-boundary',label='positive_boundary',source_url=STOCKCHARTS,
             provenance='Publisher-labeled EMC historical positive; retrospective, not an independently labeled as-of input.',
             lesson='The published EMC example has a sharp initial decline, a base extending over two months, and an approximately six-week handle. A sharp drop, a gap, or a handle longer than twenty sessions is not automatically a semantic failure.'),
        dict(id='fidelity-structure',label='boundary',source_url=FIDELITY,
             provenance='Paraphrased structural teaching, not a labeled stock observation.',
             lesson='The structure is a rounded base followed by an upper consolidation. Ideal equal rims are not mandatory. A projected cup-height objective is a guideline, not evidence that an entry must succeed.'),
        dict(id='schematic-u',label='positive_illustration',source_url=STOCKCHARTS,
             provenance='Project-made schematic informed by published structure; synthetic, not a market example.',
             lesson='A decline spreads into a sustained low base, then recovers; the later shallow upper pullback attaches to that recovery.'),
        dict(id='schematic-v',label='negative_illustration',source_url=STOCKCHARTS,
             provenance='Project-made counterexample to the source’s U-versus-V distinction; synthetic, not publisher-labeled data.',
             lesson='An isolated down-and-immediate-up reversal with no sustained base is not a rounded cup. Do not generalize this into a ban on every gap or steep portion.'),
        dict(id='schematic-detached',label='negative_illustration',source_url=STOCKCHARTS,
             provenance='Project-made disconnected-sequence counterexample; synthetic, not a market label.',
             lesson='A much later pullback after a separate large advance must not be spliced onto an old cup. Rising breakout bars do not themselves prove that the preceding handle is absent.'),
    ]
}


def reference_pack():
    return deepcopy(PACK)


def reference_chart_png():
    import io
    from matplotlib.figure import Figure
    fig=Figure(figsize=(12,3),dpi=90,facecolor='#fafaf7')
    cases=[('schematic-u',[100,96,91,88,87,87,88,91,96,100,99,97,98,101]),
           ('schematic-v',[100,99,98,97,96,80,96,98,100,99,98,99,101]),
           ('schematic-detached',[100,94,88,87,88,94,100,108,115,120,117,115,119,122])]
    for ax,(name,values) in zip(fig.subplots(1,3),cases):
        ax.plot(values,color='#235e51',linewidth=2)
        ax.set_title(name,fontsize=11);ax.set_xlabel('Illustrative sequence')
        ax.set_ylabel('Synthetic normalized price');ax.grid(alpha=.15)
    fig.suptitle('PROJECT-MADE SCHEMATICS — NOT STOCK DATA OR MARKET ACCURACY LABELS',fontsize=10)
    fig.tight_layout();buf=io.BytesIO();fig.savefig(buf,format='png');return buf.getvalue()
