FROM node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS web
WORKDIR /build
RUN npm install --global pnpm@11.25.0
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
COPY LICENSE THIRD_PARTY_NOTICES.txt DATA_NOTICE.md DATA_NOTICE.zh-CN.md /
COPY examples/cup-handle/config.json examples/cup-handle/result.json /examples/cup-handle/
COPY examples/builder/cup-complete/ /examples/builder/cup-complete/
COPY examples/builder/nvda-revision/ /examples/builder/nvda-revision/
COPY docs/media/builder-conversation.png docs/media/walkthrough.mp4 docs/media/walkthrough.bilingual.srt docs/media/revision.gif /docs/media/
RUN pnpm build

FROM python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72
WORKDIR /app
COPY requirements-runtime.lock ./
RUN pip install --no-cache-dir -r requirements-runtime.lock && pip check
COPY LICENSE THIRD_PARTY_NOTICES.txt DATA_NOTICE.md DATA_NOTICE.zh-CN.md ./
COPY lab/ ./lab/
COPY scripts/freeze_market.py ./scripts/freeze_market.py
COPY docs/en/execution-contract.md ./docs/en/execution-contract.md
COPY examples/cup-handle/config.json examples/cup-handle/result.json ./examples/cup-handle/
COPY examples/builder/cup-complete/project.json ./examples/builder/cup-complete/
COPY examples/builder/nvda-revision/project.json ./examples/builder/nvda-revision/
COPY --from=web /build/dist ./web/dist/
ENV LAB_DATA_ROOT=/data LAB_EXECUTION_BACKEND=docker PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib
EXPOSE 8765
CMD ["python", "-m", "lab.container_app"]
