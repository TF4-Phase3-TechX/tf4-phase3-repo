{{/*
Expand the name of the chart.
*/}}
{{- define "techx-corp.name" -}}
{{- default .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "techx-corp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "techx-corp.labels" -}}
helm.sh/chart: {{ include "techx-corp.chart" . }}
{{ include "techx-corp.selectorLabels" . }}
{{ include "techx-corp.workloadLabels" . }}
app.kubernetes.io/part-of: techx-corp
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}



{{/*
Workload (Pod) labels
*/}}
{{- define "techx-corp.workloadLabels" -}}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- if .name }}
app.kubernetes.io/component: {{ .name}}
app.kubernetes.io/name: {{ .name }}
{{- end }}
{{- end }}




{{/*
Selector labels
*/}}
{{- define "techx-corp.selectorLabels" -}}
{{- if .name }}
opentelemetry.io/name: {{ .name }}
{{- end }}
{{- end }}

{{/*
Render a component image reference. When digest is set, keep the readable tag and
pin the immutable artifact with repo:tag@sha256:...
*/}}
{{- define "techx-corp.image" -}}
{{- $imageOverride := .imageOverride | default dict -}}
{{- $repository := (get $imageOverride "repository") | default .defaultValues.image.repository -}}
{{- $tag := (get $imageOverride "tag") | default (printf "%s-%s" (default .Chart.AppVersion .defaultValues.image.tag) .name) -}}
{{- $digest := (get $imageOverride "digest") | default "" -}}
{{- if $digest -}}
{{- printf "%s:%s@%s" $repository $tag $digest -}}
{{- else -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end }}

{{- define "techx-corp.envOverriden" -}}
{{- $mergedEnvs := list }}
{{- $envOverrides := default (list) .envOverrides }}

{{- range .env }}
{{-   $currentEnv := . }}
{{-   $hasOverride := false }}
{{-   range $envOverrides }}
{{-     if eq $currentEnv.name .name }}
{{-       $mergedEnvs = append $mergedEnvs . }}
{{-       $envOverrides = without $envOverrides . }}
{{-       $hasOverride = true }}
{{-     end }}
{{-   end }}
{{-   if not $hasOverride }}
{{-     $mergedEnvs = append $mergedEnvs $currentEnv }}
{{-   end }}
{{- end }}
{{- $mergedEnvs = concat $mergedEnvs $envOverrides }}
{{- mustToJson $mergedEnvs }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "techx-corp.serviceAccountName" -}}
{{- if .serviceAccount.create }}
{{- default (include "techx-corp.name" .) .serviceAccount.name }}
{{- else }}
{{- default "default" .serviceAccount.name }}
{{- end }}
{{- end }}
