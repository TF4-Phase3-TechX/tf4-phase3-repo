{{/*
Demo component Deployment template
*/}}
{{- define "techx-corp.deployment" }}
{{- $autoscaling := .autoscaling | default dict }}
{{- /* Ref: CDO08-REL-16 - Blue-Green cutover for cart via Argo Rollouts. */}}
{{- $rolloutsEnabled := (.rollouts).enabled | default false }}
---
apiVersion: {{ if $rolloutsEnabled }}argoproj.io/v1alpha1{{ else }}apps/v1{{ end }}
kind: {{ if $rolloutsEnabled }}Rollout{{ else }}Deployment{{ end }}
metadata:
  name: {{ .name }}
  labels:
    {{- include "techx-corp.labels" . | nindent 4 }}
spec:
  {{- if not ($autoscaling.enabled | default false) }}
  replicas: {{ .replicas | default .defaultValues.replicas }}
  {{- end }}
  revisionHistoryLimit: {{ .revisionHistoryLimit | default .defaultValues.revisionHistoryLimit }}
  {{- if $rolloutsEnabled }}
  strategy:
    blueGreen:
      activeService: {{ .name }}
      autoPromotionEnabled: false
  {{- else if .strategy }}
  strategy:
    {{- .strategy | toYaml | nindent 4 }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "techx-corp.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "techx-corp.selectorLabels" . | nindent 8 }}
        {{- include "techx-corp.workloadLabels" . | nindent 8 }}
        {{- if .podLabels }}
        {{- toYaml .podLabels | nindent 8 }}
        {{- end }}
      {{- if .podAnnotations }}
      annotations:
        {{- toYaml .podAnnotations | nindent 8 }}
      {{- end }}
    spec:
      {{- if or .defaultValues.image.pullSecrets ((.imageOverride).pullSecrets) }}
      imagePullSecrets:
        {{- ((.imageOverride).pullSecrets) | default .defaultValues.image.pullSecrets | toYaml | nindent 8}}
      {{- end }}
      serviceAccountName: {{ .serviceAccountName | default (include "techx-corp.serviceAccountName" .) }}
      {{- $schedulingRules := .schedulingRules | default dict }}
      {{- if or .defaultValues.schedulingRules.nodeSelector $schedulingRules.nodeSelector}}
      nodeSelector:
        {{- $schedulingRules.nodeSelector | default .defaultValues.schedulingRules.nodeSelector | toYaml | nindent 8 }}
      {{- end }}
      {{- if or .defaultValues.schedulingRules.affinity $schedulingRules.affinity}}
      affinity:
        {{- $schedulingRules.affinity | default .defaultValues.schedulingRules.affinity | toYaml | nindent 8 }}
      {{- end }}
      {{- if or .defaultValues.schedulingRules.tolerations $schedulingRules.tolerations}}
      tolerations:
        {{- $schedulingRules.tolerations | default .defaultValues.schedulingRules.tolerations | toYaml | nindent 8 }}
      {{- end }}
      {{- if or .defaultValues.schedulingRules.topologySpreadConstraints $schedulingRules.topologySpreadConstraints}}
      topologySpreadConstraints:
        {{- $schedulingRules.topologySpreadConstraints | default .defaultValues.schedulingRules.topologySpreadConstraints | toYaml | nindent 8 }}
      {{- end }}
      {{- if or .defaultValues.podSecurityContext .podSecurityContext }}
      securityContext:
        {{- .podSecurityContext | default .defaultValues.podSecurityContext | toYaml | nindent 8 }}
      {{- end}}
      containers:
        - name: {{ .name }}
          image: '{{ include "techx-corp.image" . }}'
          imagePullPolicy: {{ ((.imageOverride).pullPolicy) | default .defaultValues.image.pullPolicy }}
          {{- if .command }}
          command:
            {{- .command | toYaml | nindent 12 -}}
          {{- end }}
          {{- if or .ports .service}}
          ports:
            {{- include "techx-corp.pod.ports" . | nindent 12 }}
          {{- end }}
          env:
            {{- include "techx-corp.pod.env" . | nindent 12 }}
          resources:
            {{- .resources | toYaml | nindent 12 }}
          {{- if or .defaultValues.securityContext .securityContext }}
          securityContext:
            {{- .securityContext | default .defaultValues.securityContext | toYaml | nindent 12 }}
          {{- end}}
          {{- if .livenessProbe }}
          livenessProbe:
            {{- .livenessProbe | toYaml | nindent 12 }}
          {{- end }}
          {{- if .readinessProbe }}
          readinessProbe:
            {{- .readinessProbe | toYaml | nindent 12 }}
          {{- end }}
          volumeMounts:
            {{- if .additionalVolumeMounts }}
            {{- tpl (toYaml .additionalVolumeMounts) . | nindent 12 }}
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
            {{- .command | toYaml | nindent 12 -}}
          {{- end }}
          {{- if or .ports .service }}
          ports:
            {{- include "techx-corp.pod.ports" . | nindent 12 }}
          {{- end }}
          env:
            {{- include "techx-corp.pod.env" . | nindent 12 }}
          {{- if .resources }}
          resources:
            {{- .resources | toYaml | nindent 12 }}
          {{- end }}
          {{- if or .defaultValues.securityContext .securityContext }}
          securityContext:
            {{- .securityContext | default .defaultValues.securityContext | toYaml | nindent 12 }}
          {{- end}}
          {{- if .livenessProbe }}
          livenessProbe:
            {{- .livenessProbe | toYaml | nindent 12 }}
          {{- end }}
          {{- if .readinessProbe }}
          readinessProbe:
            {{- .readinessProbe | toYaml | nindent 12 }}
          {{- end }}
          {{- if .volumeMounts }}
          volumeMounts:
            {{- .volumeMounts | toYaml | nindent 12 }}
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
        {{- tpl (toYaml $activeInits) . | nindent 8 }}
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
        {{- tpl (toYaml .additionalVolumes) . | nindent 8 }}
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
    {{- include "techx-corp.selectorLabels" . | nindent 4 }}
{{- end}}
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
