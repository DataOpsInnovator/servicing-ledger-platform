{{- define "ledger.image" -}}
{{- $digest := required "image.digest is required" .Values.image.digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" $digest) -}}{{ fail "image.digest must be a SHA256 digest" }}{{- end -}}
{{- printf "%s@%s" (required "image.repository is required" .Values.image.repository) $digest -}}
{{- end -}}
{{- define "ledger.podSecurity" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
seccompProfile:
  type: RuntimeDefault
{{- end -}}
{{- define "ledger.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end -}}
{{- define "ledger.env" -}}
{{- $root := .root -}}
- name: SERVICING_ENV
  value: cloud
- name: AUTO_MIGRATE
  value: "false"
- name: AWS_REGION
  value: {{ $root.Values.aws.region | quote }}
- name: AWS_DEFAULT_REGION
  value: {{ $root.Values.aws.region | quote }}
- name: DATABASE_SECRET_ARN
  value: {{ required (printf "databaseSecrets.%s is required" .role) (index $root.Values.aws.databaseSecrets .role) | quote }}
- name: SQS_QUEUE_URL
  value: {{ required "aws.queueUrl is required" $root.Values.aws.queueUrl | quote }}
- name: AUDIT_BUCKET
  value: {{ required "aws.auditBucket is required" $root.Values.aws.auditBucket | quote }}
{{- if eq .role "api" }}
- name: OIDC_ISSUER
  value: {{ required "identity.issuer is required" $root.Values.identity.issuer | quote }}
- name: OIDC_AUDIENCE
  value: {{ required "identity.audience is required" $root.Values.identity.audience | quote }}
- name: OIDC_JWKS_URL
  value: {{ required "identity.jwksUrl is required" $root.Values.identity.jwksUrl | quote }}
{{- if $root.Values.observability.otlpEndpoint }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ $root.Values.observability.otlpEndpoint | quote }}
{{- end }}
{{- end }}
{{- end -}}
{{- define "ledger.mounts" -}}
- name: rds-ca
  mountPath: /etc/rds-ca
  readOnly: true
- name: tmp
  mountPath: /tmp
{{- end -}}
{{- define "ledger.volumes" -}}
- name: rds-ca
  configMap:
    name: {{ .Values.aws.caConfigMap }}
- name: tmp
  emptyDir:
    sizeLimit: 32Mi
{{- end -}}
