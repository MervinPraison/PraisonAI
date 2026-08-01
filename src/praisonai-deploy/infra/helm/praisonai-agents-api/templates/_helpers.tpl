{{- define "praisonai-agents-api.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "praisonai-agents-api.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "praisonai-agents-api.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "praisonai-agents-api.labels" -}}
app.kubernetes.io/name: {{ include "praisonai-agents-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- end -}}

{{- define "praisonai-agents-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "praisonai-agents-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "praisonai-agents-api.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "praisonai-agents-api.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "praisonai-agents-api.authSecretName" -}}
{{- if .Values.auth.existingSecret -}}
{{- .Values.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-auth" (include "praisonai-agents-api.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "praisonai-agents-api.postgresSecretName" -}}
{{- if .Values.postgres.auth.existingSecret -}}
{{- .Values.postgres.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-postgres" (include "praisonai-agents-api.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "praisonai-agents-api.agentsConfigMapName" -}}
{{- if .Values.agents.existingConfigMap -}}
{{- .Values.agents.existingConfigMap -}}
{{- else if .Values.agents.configMapName -}}
{{- .Values.agents.configMapName -}}
{{- else -}}
{{- printf "%s-agents" (include "praisonai-agents-api.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "praisonai-agents-api.validateAuth" -}}
{{- if .Values.auth.enabled -}}
{{- if and (not .Values.auth.existingSecret) (not .Values.auth.token) -}}
{{- fail "auth.enabled is true but no auth.existingSecret or auth.token was provided." -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "praisonai-agents-api.validatePostgres" -}}
{{- if .Values.postgres.enabled -}}
{{- if and (not .Values.postgres.auth.existingSecret) (not .Values.postgres.auth.password) -}}
{{- fail "postgres.enabled is true but no postgres.auth.existingSecret or postgres.auth.password was provided." -}}
{{- end -}}
{{- end -}}
{{- end -}}
