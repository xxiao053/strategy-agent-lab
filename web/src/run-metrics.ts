type MetricRun={assumptions?:{initial_cash?:number};curve?:readonly {equity:number}[]};

export function runMetrics(run:MetricRun){
  const initial=run.assumptions?.initial_cash,curve=run.curve;
  if(typeof initial!=='number'||!Number.isFinite(initial)||initial<=0||!curve?.length||curve.some(point=>!Number.isFinite(point.equity)))return null;
  let peak=initial,maxDrawdown=0;
  for(const point of curve){
    peak=Math.max(peak,point.equity);
    maxDrawdown=Math.max(maxDrawdown,(peak-point.equity)/peak);
  }
  return {totalReturn:(curve.at(-1)!.equity-initial)/initial,maxDrawdown};
}
