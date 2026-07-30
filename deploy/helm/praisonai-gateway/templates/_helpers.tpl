{{- define "praisonai-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "praisonai-gateway.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "praisonai-gateway.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "praisonai-gateway.labels" -}}
app.kubernetes.io/name: {{ include "praisonai-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- end -}}

{{- define "praisonai-gateway.selectorLabels" -}}
app.kubernetes.io/name: {{ include "praisonai-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "praisonai-gateway.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "praisonai-gateway.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Name of the secret holding GATEWAY_AUTH_TOKEN (existing or chart-managed). */}}
{{- define "praisonai-gateway.authSecretName" -}}
{{- if .Values.auth.existingSecret -}}
{{- .Values.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-auth" (include "praisonai-gateway.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/* Fail fast on insecure configuration: auth enabled + exposed via ingress but no token. */}}
{{- define "praisonai-gateway.validateAuth" -}}
{{- if and .Values.auth.enabled .Values.ingress.enabled -}}
{{- if and (not .Values.auth.existingSecret) (not .Values.auth.token) -}}
{{- fail "auth.enabled and ingress.enabled are true but no auth.existingSecret or auth.token was provided. Refusing to expose the gateway without a GATEWAY_AUTH_TOKEN." -}}
{{- end -}}
{{- end -}}
{{- end -}}
