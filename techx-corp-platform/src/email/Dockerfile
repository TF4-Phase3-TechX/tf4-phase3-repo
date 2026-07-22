# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM docker.io/library/ruby:3.4-alpine3.23@sha256:aee2f8ad808abff4aecaa1d36340dce22e6b1eb9b88216ed18be4245c4324d9b AS builder

COPY ./src/email/Gemfile Gemfile
COPY ./src/email/Gemfile.lock Gemfile.lock

RUN apk add --no-cache make gcc musl-dev gcompat && \
    bundle install

FROM docker.io/library/ruby:3.4-alpine3.23@sha256:aee2f8ad808abff4aecaa1d36340dce22e6b1eb9b88216ed18be4245c4324d9b

COPY --from=builder /usr/local/bundle/ /usr/local/bundle/

WORKDIR /email_server

COPY ./src/email/views/ views/

COPY ./src/email/.ruby-version .ruby-version
COPY ./src/email/Gemfile Gemfile
COPY ./src/email/Gemfile.lock Gemfile.lock
COPY ./src/email/email_server.rb email_server.rb

EXPOSE ${EMAIL_PORT}
ENTRYPOINT ["bundle", "exec", "ruby", "email_server.rb"]
