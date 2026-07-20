{{/*
Get Pod Env
- Merges default environment variables (if used) with component environment variables.
- If using defaults, will pull out OTEL_RESOURCE_ATTRIBUTES from the list to be reused later.
- An environment variable named OTEL_RESOURCE_ATTRIBUTES_EXTRA will have its value appended to the value of the
OTEL_RESOURCE_ATTRIBUTES environment variable if it exists.
- The OTEL_RESOURCES_ATTRIBUTES environment variable will typically use Kubernetes environment variable expansion and
should be last.
*/}}
{{- define "techx-corp.pod.env" -}}
{{- $resourceAttributesEnv := dict }}
{{- $allEnvs := list }}

{{- if .useDefault.env  }}
{{-   $defaultEnvs := include "techx-corp.envOverriden" (dict "env" .defaultValues.env "envOverrides" .defaultValues.envOverrides) | mustFromJson }}
{{-   range $defaultEnvs }}
{{-     if eq .name "OTEL_RESOURCE_ATTRIBUTES" }}
{{-       $resourceAttributesEnv = . }}
{{-     else }}
{{-       $allEnvs = append $allEnvs . }}
{{-     end }}
{{-   end }}
{{- end }}

{{- if or .env .envOverrides }}
{{-   $localEnvs := include "techx-corp.envOverriden" . | mustFromJson }}
{{-   range $localEnvs }}
{{-     if eq .name "OTEL_RESOURCE_ATTRIBUTES" }}
{{-       $resourceAttributesEnv = . }}
{{-     else if and $resourceAttributesEnv (eq .name "OTEL_RESOURCE_ATTRIBUTES_EXTRA") }}
{{-       $newValue := (printf "%s,%s" (get $resourceAttributesEnv "value") .value) }}
{{-       $resourceAttributesEnv = dict "name" "OTEL_RESOURCE_ATTRIBUTES" "value" $newValue }}
{{-     else }}
{{-       $allEnvs = append $allEnvs . }}
{{-     end }}
{{-   end }}
{{- end }}

{{- if $resourceAttributesEnv }}
{{-   $allEnvs = append $allEnvs $resourceAttributesEnv }}
{{- end }}

{{/*
CDO08-SEC-13D: When managedData.<type>.enabled=true, replace the matching
plaintext env var with a secretKeyRef pointing to the ESO-synced K8s Secret.
All flags default to false — no change to existing behavior until explicitly flipped.
*/}}
{{- $md := .managedData | default dict }}
{{- $managedDataEnabled := (($md).enabled | default false) }}

{{- if and $managedDataEnabled (($md.postgresql | default dict).enabled | default false) }}
{{-   $pgSecret := ($md.postgresql).secretName | default "rds-postgres-secret" }}
{{-   $pgKeyMap := dict "accounting" "dotnet-conn-string" "product-catalog" "go-conn-string" "product-reviews" "python-conn-string" }}
{{-   if hasKey $pgKeyMap .name }}
{{-     $allEnvs = include "techx-corp.replaceEnvWithSecretRef" (dict "envList" $allEnvs "envName" "DB_CONNECTION_STRING" "secretName" $pgSecret "secretKey" (index $pgKeyMap .name)) | mustFromJson }}
{{-   end }}
{{- end }}

{{- if and $managedDataEnabled (($md.valkey | default dict).enabled | default false) }}
{{-   $valkeySecret := ($md.valkey).secretName | default "elasticache-valkey-secret" }}
{{-   if eq .name "cart" }}
{{-     $allEnvs = include "techx-corp.replaceEnvWithSecretRef" (dict "envList" $allEnvs "envName" "VALKEY_ADDR" "secretName" $valkeySecret "secretKey" "valkey-address") | mustFromJson }}
{{-   end }}
{{- end }}

{{- if and $managedDataEnabled (($md.kafka | default dict).enabled | default false) }}
{{-   $kafkaSecret := ($md.kafka).secretName | default "msk-kafka-secret" }}
{{-   if has .name (list "accounting" "checkout" "fraud-detection") }}
{{-     $allEnvs = include "techx-corp.replaceEnvWithSecretRef" (dict "envList" $allEnvs "envName" "KAFKA_ADDR" "secretName" $kafkaSecret "secretKey" "kafka-address") | mustFromJson }}
{{-     $allEnvs = include "techx-corp.upsertEnvSecretRef" (dict "envList" $allEnvs "envName" "KAFKA_SECURITY_PROTOCOL" "secretName" $kafkaSecret "secretKey" "security-protocol") | mustFromJson }}
{{-     $allEnvs = include "techx-corp.upsertEnvSecretRef" (dict "envList" $allEnvs "envName" "KAFKA_SASL_MECHANISM" "secretName" $kafkaSecret "secretKey" "sasl-mechanism") | mustFromJson }}
{{-     $allEnvs = include "techx-corp.upsertEnvSecretRef" (dict "envList" $allEnvs "envName" "KAFKA_USERNAME" "secretName" $kafkaSecret "secretKey" "username") | mustFromJson }}
{{-     $allEnvs = include "techx-corp.upsertEnvSecretRef" (dict "envList" $allEnvs "envName" "KAFKA_PASSWORD" "secretName" $kafkaSecret "secretKey" "password") | mustFromJson }}
{{-   end }}
{{- end }}

{{- tpl (toYaml $allEnvs) . }}
{{- end }}

{{/*
Helper: replace a named env var in an env list with a secretKeyRef entry.
Input dict keys: envList, envName, secretName, secretKey.
Returns a JSON array suitable for mustFromJson chaining.
*/}}
{{- define "techx-corp.replaceEnvWithSecretRef" -}}
{{- $out := list }}
{{- range .envList }}
{{-   if eq .name $.envName }}
{{-     $out = append $out (dict "name" $.envName "valueFrom" (dict "secretKeyRef" (dict "name" $.secretName "key" $.secretKey))) }}
{{-   else }}
{{-     $out = append $out . }}
{{-   end }}
{{- end }}
{{- $out | toJson }}
{{- end }}

{{/*
Helper: upsert a named env var as a secretKeyRef entry.
Input dict keys: envList, envName, secretName, secretKey.
Returns a JSON array suitable for mustFromJson chaining.
*/}}
{{- define "techx-corp.upsertEnvSecretRef" -}}
{{- $out := list }}
{{- $found := false }}
{{- range .envList }}
{{-   if eq .name $.envName }}
{{-     $out = append $out (dict "name" $.envName "valueFrom" (dict "secretKeyRef" (dict "name" $.secretName "key" $.secretKey))) }}
{{-     $found = true }}
{{-   else }}
{{-     $out = append $out . }}
{{-   end }}
{{- end }}
{{- if not $found }}
{{-   $out = append $out (dict "name" .envName "valueFrom" (dict "secretKeyRef" (dict "name" .secretName "key" .secretKey))) }}
{{- end }}
{{- $out | toJson }}
{{- end }}


{{/*
Get Pod ports
*/}}
{{- define "techx-corp.pod.ports" -}}
{{- if .ports }}
{{-   range $port := .ports }}
- containerPort: {{ $port.value }}
  name: {{ $port.name}}
{{-   end }}
{{- end }}
{{- if .service }}
{{-   if .service.port }}
- containerPort: {{.service.port}}
  name: service
{{-   end }}
{{- end }}
{{- end }}
