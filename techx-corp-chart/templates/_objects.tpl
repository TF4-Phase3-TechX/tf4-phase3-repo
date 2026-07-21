{{/*
Demo component Deployment template
*/}}
{{- define "techx-corp.deployment" }}
{{- $autoscaling := .autoscaling | default dict }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .name }}
  labels:
    {{- include "techx-corp.labels" . | nindent 4 }}
spec:
  {{- if not ($autoscaling.enabled | default false) }}
  replicas: {{ .replicas | default .defaultValues.replicas }}
  {{- end }}
  revisionHistoryLimit: {{ .revisionHistoryLimit | default .defaultValues.revisionHistoryLimit }}
  {{- if .strategy }}
  strategy:
    {{- .strategy | toYaml | nindent 4 }}
  {{- end }}
  {{- include "techx-corp.workloadPodSpec" . | nindent 2 }}
{{- end }}

{{/*
Argo Rollouts variant of techx-corp.deployment. Gated by rollouts.enabled (global) +
components.<name>.useRollout (per-component opt-in) in component.yaml. Shares the same
pod-template-building logic via techx-corp.workloadPodSpec so Deployment and Rollout can
never drift apart.
*/}}
{{- define "techx-corp.rollout" }}
{{- $autoscaling := .autoscaling | default dict }}
{{- $rollout := .rolloutStrategy | default dict }}
---
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: {{ .name }}
  labels:
    {{- include "techx-corp.labels" . | nindent 4 }}
spec:
  {{- if not ($autoscaling.enabled | default false) }}
  replicas: {{ .replicas | default .defaultValues.replicas }}
  {{- end }}
  revisionHistoryLimit: {{ .revisionHistoryLimit | default .defaultValues.revisionHistoryLimit }}
  strategy:
    {{- if $rollout.canary }}
    canary:
      {{- $rollout.canary | toYaml | nindent 6 }}
    {{- else if $rollout.blueGreen }}
    blueGreen:
      activeService: {{ ($rollout.blueGreen).activeService | default .name }}
      previewService: {{ ($rollout.blueGreen).previewService | default (printf "%s-preview" .name) }}
      {{- with (omit $rollout.blueGreen "activeService" "previewService") }}
      {{- toYaml . | nindent 6 }}
      {{- end }}
    {{- else }}
    {{- fail (printf "components.%s.useRollout is true but rolloutStrategy.canary or rolloutStrategy.blueGreen must be set" .name) }}
    {{- end }}
  {{- include "techx-corp.workloadPodSpec" . | nindent 2 }}
{{- end }}

{{/*
Shared selector + pod template spec, used by both techx-corp.deployment and techx-corp.rollout.
Caller must include this directly under `spec:` via `{{- include "techx-corp.workloadPodSpec" . | nindent 2 }}`.
*/}}
{{- define "techx-corp.workloadPodSpec" -}}
selector:
  matchLabels:
    {{- include "techx-corp.selectorLabels" . | nindent 4 }}
template:
  metadata:
    labels:
      {{- include "techx-corp.selectorLabels" . | nindent 6 }}
      {{- include "techx-corp.workloadLabels" . | nindent 6 }}
      {{- if .podLabels }}
      {{- toYaml .podLabels | nindent 6 }}
      {{- end }}
    {{- if .podAnnotations }}
    annotations:
      {{- toYaml .podAnnotations | nindent 6 }}
    {{- end }}
  spec:
    {{- if or .defaultValues.image.pullSecrets ((.imageOverride).pullSecrets) }}
    imagePullSecrets:
      {{- ((.imageOverride).pullSecrets) | default .defaultValues.image.pullSecrets | toYaml | nindent 6}}
    {{- end }}
    serviceAccountName: {{ .serviceAccountName | default (include "techx-corp.serviceAccountName" .) }}
    {{- $schedulingRules := .schedulingRules | default dict }}
    {{- if or .defaultValues.schedulingRules.nodeSelector $schedulingRules.nodeSelector}}
    nodeSelector:
      {{- $schedulingRules.nodeSelector | default .defaultValues.schedulingRules.nodeSelector | toYaml | nindent 6 }}
    {{- end }}
    {{- if or .defaultValues.schedulingRules.affinity $schedulingRules.affinity}}
    affinity:
      {{- $schedulingRules.affinity | default .defaultValues.schedulingRules.affinity | toYaml | nindent 6 }}
    {{- end }}
    {{- if or .defaultValues.schedulingRules.tolerations $schedulingRules.tolerations}}
    tolerations:
      {{- $schedulingRules.tolerations | default .defaultValues.schedulingRules.tolerations | toYaml | nindent 6 }}
    {{- end }}
    {{- if or .defaultValues.schedulingRules.topologySpreadConstraints $schedulingRules.topologySpreadConstraints}}
    topologySpreadConstraints:
      {{- $schedulingRules.topologySpreadConstraints | default .defaultValues.schedulingRules.topologySpreadConstraints | toYaml | nindent 6 }}
    {{- end }}
    {{- if or .defaultValues.podSecurityContext .podSecurityContext }}
    securityContext:
      {{- .podSecurityContext | default .defaultValues.podSecurityContext | toYaml | nindent 6 }}
    {{- end}}
    containers:
      - name: {{ .name }}
        image: '{{ include "techx-corp.image" . }}'
        imagePullPolicy: {{ ((.imageOverride).pullPolicy) | default .defaultValues.image.pullPolicy }}
        {{- if .command }}
        command:
          {{- .command | toYaml | nindent 10 -}}
        {{- end }}
        {{- if or .ports .service}}
        ports:
          {{- include "techx-corp.pod.ports" . | nindent 10 }}
        {{- end }}
        env:
          {{- include "techx-corp.pod.env" . | nindent 10 }}
        resources:
          {{- .resources | toYaml | nindent 10 }}
        {{- if or .defaultValues.securityContext .securityContext }}
        securityContext:
          {{- .securityContext | default .defaultValues.securityContext | toYaml | nindent 10 }}
        {{- end}}
        {{- if .livenessProbe }}
        livenessProbe:
          {{- .livenessProbe | toYaml | nindent 10 }}
        {{- end }}
        {{- if .readinessProbe }}
        readinessProbe:
          {{- .readinessProbe | toYaml | nindent 10 }}
        {{- end }}
        volumeMounts:
          {{- if .additionalVolumeMounts }}
          {{- tpl (toYaml .additionalVolumeMounts) . | nindent 10 }}
          {{- end }}
        {{- range .mountedConfigMaps }}
          - name: {{ .name | lower }}
            mountPath: {{ .mountPath }}
            {{- if .subPath }}
            subPath: {{ .subPath }}
            {{- end }}
        {{- end }}
        {{- range .mountedEmptyDirs }}
          - name: {{ .name | lower }}
            mountPath: {{ .mountPath }}
            {{- if .subPath }}
            subPath: {{ .subPath }}
            {{- end }}
        {{- end }}
      {{- range .sidecarContainers }}
      {{- $sidecar := set . "name" (.name | lower)}}
      {{- $sidecar := set . "Chart" $.Chart }}
      {{- $sidecar := set . "Release" $.Release }}
      {{- $sidecar := set . "defaultValues" $.defaultValues }}
      - name: {{ .name   }}
        image: '{{ include "techx-corp.image" . }}'
        imagePullPolicy: {{ ((.imageOverride).pullPolicy) | default .defaultValues.image.pullPolicy }}
        {{- if .command }}
        command:
          {{- .command | toYaml | nindent 10 -}}
        {{- end }}
        {{- if or .ports .service }}
        ports:
          {{- include "techx-corp.pod.ports" . | nindent 10 }}
        {{- end }}
        env:
          {{- include "techx-corp.pod.env" . | nindent 10 }}
        {{- if .resources }}
        resources:
          {{- .resources | toYaml | nindent 10 }}
        {{- end }}
        {{- if or .defaultValues.securityContext .securityContext }}
        securityContext:
          {{- .securityContext | default .defaultValues.securityContext | toYaml | nindent 10 }}
        {{- end}}
        {{- if .livenessProbe }}
        livenessProbe:
          {{- .livenessProbe | toYaml | nindent 10 }}
        {{- end }}
        {{- if .readinessProbe }}
        readinessProbe:
          {{- .readinessProbe | toYaml | nindent 10 }}
        {{- end }}
        {{- if .volumeMounts }}
        volumeMounts:
          {{- .volumeMounts | toYaml | nindent 10 }}
        {{- end }}
      {{- end }}
    {{- if .initContainers }}
    initContainers:
      {{- $md := .managedData | default dict }}
      {{- $managedDataEnabled := (($md).enabled | default false) }}
      {{- $skipKafkaInit := and $managedDataEnabled (($md.kafka | default dict).enabled | default false) }}
      {{- $skipValkeyInit := and $managedDataEnabled (($md.valkey | default dict).enabled | default false) }}
      {{- $activeInits := list }}
      {{- range .initContainers }}
      {{-   if and $skipKafkaInit (eq .name "wait-for-kafka") }}
      {{-   else if and $skipValkeyInit (eq .name "wait-for-valkey-cart") }}
      {{-   else }}
      {{-     $activeInits = append $activeInits . }}
      {{-   end }}
      {{- end }}
      {{- tpl (toYaml $activeInits) . | nindent 6 }}
    {{- end}}
    volumes:
      {{- range .mountedConfigMaps }}
      - name: {{ .name | lower}}
        configMap:
          {{- if .existingConfigMap }}
          name: {{ tpl .existingConfigMap $ }}
          {{- else }}
          name: {{ $.name }}-{{ .name | lower }}
          {{- end }}
      {{- end }}
      {{- range .mountedEmptyDirs }}
      - name: {{ .name | lower}}
        emptyDir: {}
      {{- end }}
      {{- if .additionalVolumes }}
      {{- tpl (toYaml .additionalVolumes) . | nindent 6 }}
      {{- end }}
{{- end }}

{{/*
Demo component Service template
*/}}
{{- define "techx-corp.service" }}
{{- if or .ports .service}}
{{- $service := .service | default dict }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .name }}
  labels:
    {{- include "techx-corp.labels" . | nindent 4 }}
  {{- with $service.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- include "techx-corp.servicePodPorts" . | nindent 2 }}
{{- end}}
{{- end}}

{{/*
Argo Rollouts blue-green preview Service. Emitted alongside techx-corp.service (the active
Service) only when a component opts into rolloutStrategy.blueGreen. Argo Rollouts patches
rollouts-pod-template-hash into both Services' selectors at runtime to route traffic; the
chart only needs to make sure both Service objects exist with matching ports/selector.
*/}}
{{- define "techx-corp.rolloutPreviewService" }}
{{- $service := .service | default dict }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .name }}-preview
  labels:
    {{- include "techx-corp.labels" . | nindent 4 }}
  {{- with $service.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- include "techx-corp.servicePodPorts" . | nindent 2 }}
{{- end}}

{{/*
Shared Service spec body (type/ports/selector), used by both techx-corp.service and
techx-corp.rolloutPreviewService. Caller must include this directly under `spec:` via
`{{- include "techx-corp.servicePodPorts" . | nindent 2 }}`.
*/}}
{{- define "techx-corp.servicePodPorts" }}
{{- $service := .service | default dict -}}
type: {{ $service.type | default "ClusterIP" }}
ports:
  {{- if .ports }}
  {{- range .ports }}
  - port: {{ .value }}
    name: {{ .name}}
    targetPort: {{ .value }}
  {{- end }}
  {{- end }}

  {{- if and .service .service.port }}
  - port: {{ .service.port}}
    name: tcp-service
    targetPort: {{ .service.port }}
  {{- if .service.nodePort }}
    nodePort: {{ .service.nodePort }}
  {{- end }}
  {{- end }}

  {{- range $i, $sidecar := .sidecarContainers }}
  {{- if .ports }}
  {{- range .ports }}
  - port: {{ .value }}
    name: {{ .name}}
    targetPort: {{ .value }}
  {{- end }}
  {{- end }}

  {{- if and .service .service.port }}
  - port: {{ .service.port}}
    name: tcp-service-{{ $i }}
    targetPort: {{ .service.port }}
  {{- if .service.nodePort }}
    nodePort: {{ .service.nodePort }}
  {{- end }}
  {{- end }}
  {{- end }}
selector:
  {{- include "techx-corp.selectorLabels" . | nindent 2 }}
{{- end}}

{{/*
Demo component ConfigMap template
*/}}
{{- define "techx-corp.configmap" }}
{{- range .mountedConfigMaps }}
{{- if .data }}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $.name }}-{{ .name | lower }}
  labels:
        {{- include "techx-corp.labels" $ | nindent 4 }}
data:
  {{- .data | toYaml | nindent 2}}
{{- end}}
{{- end}}
{{- end}}

{{/*
Demo component Ingress template
*/}}
{{- define "techx-corp.ingress" }}
{{- $hasIngress := false}}
{{- if .ingress }}
{{- if .ingress.enabled }}
{{- $hasIngress = true }}
{{- end }}
{{- end }}
{{- $hasServicePorts := false}}
{{- if .service }}
{{- if .service.port }}
{{- $hasServicePorts = true }}
{{- end }}
{{- end }}
{{- if and $hasIngress (or .ports $hasServicePorts) }}
{{- $ingresses := list .ingress }}
{{- if .ingress.additionalIngresses }}
{{-   $ingresses := concat $ingresses .ingress.additionalIngresses -}}
{{- end }}
{{- range $ingresses }}
---
apiVersion: "networking.k8s.io/v1"
kind: Ingress
metadata:
  {{- if .name }}
  name: {{ $.name }}-{{ .name | lower }}
  {{- else }}
  name: {{ $.name }}
  {{- end }}
  labels:
    {{- include "techx-corp.labels" $ | nindent 4 }}
  {{- if .annotations }}
  annotations:
    {{ toYaml .annotations | nindent 4 }}
  {{- end }}
spec:
  {{- if .ingressClassName }}
  ingressClassName: {{ .ingressClassName }}
  {{- end -}}
  {{- if .tls }}
  tls:
    {{- range .tls }}
    - hosts:
        {{- range .hosts }}
        - {{ . | quote }}
        {{- end }}
      {{- with .secretName }}
      secretName: {{ . }}
      {{- end }}
    {{- end }}
  {{- end }}
  rules:
    {{- range .hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ $.name }}
                port:
                  number: {{ .port }}
          {{- end }}
    {{- end }}
{{- end}}
{{- end}}
{{- end}}
