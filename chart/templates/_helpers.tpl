{{- define "control-api.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "control-api.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "control-api.labels" -}}
app: {{ include "control-api.name" . }}
release: {{ .Release.Name }}
chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "control-api.selectorLabels" -}}
app: {{ include "control-api.name" . }}
release: {{ .Release.Name }}
{{- end }}

{{- define "control-api.migrateInitContainer" -}}
{{- if .Values.migrations.enabled }}
- name: migrate
  image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
  imagePullPolicy: {{ .Values.image.pullPolicy }}
  command: ["alembic", "upgrade", "head"]
  {{- if .Values.envSecret }}
  envFrom:
    - secretRef:
        name: {{ .Values.envSecret }}
  {{- end }}
{{- end }}
{{- end }}
