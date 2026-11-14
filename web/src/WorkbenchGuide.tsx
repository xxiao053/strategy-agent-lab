import {useLanguage} from './i18n';

export default function WorkbenchGuide(){
  const {language}=useLanguage(),t=(zh:string,en:string)=>language==='en'?en:zh;
  return <section className="bw-home bw-guide"><h1>{t('在本地运行','Run locally')}</h1>
    <p>{t('下载项目后，使用自己的模型账户创建、构建和运行策略。','Download the project to create, build and run strategies with your own model account.')}</p>
    <ol><li>{t('安装并启动 Docker，选择 Linux 容器。','Install and start Docker with Linux containers.')}</li>
      <li>{t('在项目目录启动：','Start from the project directory:')}<p>Windows</p><pre>{'.\\scripts\\start-docker.cmd'}</pre><p>macOS / Linux</p><pre>sh scripts/start-docker.sh</pre></li>
      <li>{t('打开 127.0.0.1:8765，在模型设置中配置连接，然后新建项目。','Open 127.0.0.1:8765, configure Model settings, then create a project.')}</li></ol>
    <p>{t('首次启动下载依赖，不调用模型。Windows Docker 已经过范围限定的验收；macOS / Linux 尚未完成平台验收。','First startup downloads dependencies, without model calls. Windows Docker has scoped acceptance; macOS / Linux platform acceptance is pending.')}</p>
  </section>;
}
