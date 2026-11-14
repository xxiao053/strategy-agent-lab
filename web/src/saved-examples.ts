// Exact reviewed paths only: do not bundle arbitrary local runtime/export files.
import config from '../../examples/cup-handle/config.json';
import result from '../../examples/cup-handle/result.json';
export const referenceExample={config,result};
const bundles=import.meta.glob(['../../examples/builder/cup-complete/project.json','../../examples/builder/nvda-revision/project.json'],{eager:true,import:'default'});
import {presentProject} from './ProjectPresentation';
import cupPresentation from '../../examples/builder/cup-complete/presentation.json';
import nvdaPresentation from '../../examples/builder/nvda-revision/presentation.json';
const presentations:Record<string,any>={'cup-complete':cupPresentation,'nvda-revision':nvdaPresentation};
export const savedExamples=(Object.values(bundles) as Record<string,any>[]).map(project=>presentProject(project,presentations[project.id]||{}));
// Vite configuration rejects any image outside the referenced, hash-checked closure.
const images=import.meta.glob(['../../examples/builder/cup-complete/images/*.png','../../examples/builder/nvda-revision/images/*.png'],{eager:true,query:'?url',import:'default'}) as Record<string,string>;
export function savedImageURL(hash:string){
  return /^[a-f0-9]{64}$/.test(hash)?images[`../../examples/builder/cup-complete/images/${hash}.png`]||images[`../../examples/builder/nvda-revision/images/${hash}.png`]:undefined;
}
