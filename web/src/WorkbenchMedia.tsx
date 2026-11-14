import {useLanguage} from './i18n';
import walkthrough from '../../docs/media/walkthrough.mp4?url';
import poster from '../../docs/media/builder-conversation.png?url';
import revision from '../../docs/media/revision.gif?url';
import captions from '../../docs/media/walkthrough.bilingual.srt?url';

export default function WorkbenchMedia(){
  const {language}=useLanguage(),t=(zh:string,en:string)=>language==='en'?en:zh;
  return <section className="bw-media"><h2>{t('工作流程','Workflow walkthrough')}</h2>
    <video aria-label={t('工作流程视频','Workflow video')} controls preload="none" playsInline src={walkthrough} poster={poster}/>
    <div><a href={captions} download>{t('中英字幕','English / Chinese captions')}</a><a href={revision}>{t('仓位修改过程（GIF）','Position sizing revision (GIF)')}</a></div>
  </section>;
}
