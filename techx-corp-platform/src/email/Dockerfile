# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM docker.io/library/ruby:3.4.7-alpine3.22@sha256:2a968472f07d03fd9c9fdfe220881c18fc0b28eb4d514b36b2c2d23810d70b89 AS builder

COPY ./src/email/Gemfile Gemfile
COPY ./src/email/Gemfile.lock Gemfile.lock

RUN apk update && \
    apk add make gcc musl-dev gcompat && \
    bundle install

FROM docker.io/library/ruby:3.4.7-alpine3.22@sha256:2a968472f07d03fd9c9fdfe220881c18fc0b28eb4d514b36b2c2d23810d70b89

COPY --from=builder /usr/local/bundle/ /usr/local/bundle/

WORKDIR /email_server

COPY ./src/email/views/ views/

COPY ./src/email/.ruby-version .ruby-version
COPY ./src/email/Gemfile Gemfile
COPY ./src/email/Gemfile.lock Gemfile.lock
COPY ./src/email/email_server.rb email_server.rb

EXPOSE ${EMAIL_PORT}
ENTRYPOINT ["bundle", "exec", "ruby", "email_server.rb"]
