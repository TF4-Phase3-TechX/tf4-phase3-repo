# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM docker.io/library/ruby:3.4.7-alpine3.22 AS builder

COPY ./src/email/Gemfile Gemfile
COPY ./src/email/Gemfile.lock Gemfile.lock

RUN apk update && \
    apk add make gcc musl-dev gcompat && \
    bundle install

FROM docker.io/library/ruby:3.4.7-alpine3.22

COPY --from=builder /usr/local/bundle/ /usr/local/bundle/

WORKDIR /email_server

COPY ./src/email/views/ views/

COPY ./src/email/.ruby-version .ruby-version
COPY ./src/email/Gemfile Gemfile
COPY ./src/email/Gemfile.lock Gemfile.lock
COPY ./src/email/email_server.rb email_server.rb
RUN addgroup -S -g 10001 app && \
    adduser -S -D -H -u 10001 -G app app && \
    chown -R app:app /email_server /usr/local/bundle

EXPOSE ${EMAIL_PORT}
USER 10001:10001
ENTRYPOINT ["bundle", "exec", "ruby", "email_server.rb"]
