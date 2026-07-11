# syntax=docker/dockerfile:1.7

ARG NODE_IMAGE=node:22.22.0-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.29.5-alpine3.23@sha256:42a7d7f2ee23e9f5a1dcdf3647ba5c585bbd18f79e79cd817e70e8cd61c55779

FROM ${NODE_IMAGE} AS builder

ENV COREPACK_HOME=/tmp/corepack \
    PNPM_HOME=/tmp/pnpm \
    PATH=/tmp/pnpm:$PATH
WORKDIR /build

RUN corepack enable \
    && corepack prepare pnpm@11.7.0 --activate \
    && pnpm --version

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
COPY packages/ui/package.json packages/ui/package.json
RUN --mount=type=cache,target=/tmp/pnpm-store \
    pnpm config set store-dir /tmp/pnpm-store \
    && pnpm install --frozen-lockfile

COPY apps/web apps/web
COPY packages/contracts packages/contracts
COPY packages/ui packages/ui
RUN pnpm --filter @mesh2param/contracts build \
    && pnpm --filter @mesh2param/ui build \
    && pnpm --filter @mesh2param/web build

FROM ${NGINX_IMAGE} AS runtime

USER 101:101
COPY --chown=101:101 --from=builder /build/apps/web/dist /usr/share/nginx/html
COPY --chown=101:101 infra/nginx/nginx.conf.template /etc/mesh2param/nginx.conf.template
COPY --chown=101:101 --chmod=0555 infra/nginx/entrypoint.sh /usr/local/bin/mesh2param-entrypoint
COPY --chown=101:101 LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/doc/mesh2param/
COPY --chown=101:101 licenses /usr/share/doc/mesh2param/licenses
COPY --chown=101:101 LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/nginx/html/legal/
COPY --chown=101:101 licenses /usr/share/nginx/html/legal/licenses

EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/mesh2param-entrypoint"]
CMD ["nginx", "-c", "/tmp/nginx.conf", "-g", "daemon off;"]
