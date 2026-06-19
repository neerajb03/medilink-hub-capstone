{{/*
Full image reference: <registry>/medilink/<service-name>:<tag>
*/}}
{{- define "medilink.image" -}}
{{- printf "%s/medilink/%s:%s" .Values.global.imageRegistry .serviceName .Values.global.imageTag -}}
{{- end -}}

{{/*
Standard labels applied to every resource
*/}}
{{- define "medilink.labels" -}}
app.kubernetes.io/managed-by: Helm
app.kubernetes.io/part-of: medilink-hub
{{- end -}}

{{/*
Service account name for a given microservice
*/}}
{{- define "medilink.serviceAccountName" -}}
{{- printf "sa-%s" .serviceName -}}
{{- end -}}
