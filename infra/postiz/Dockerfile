# Postiz oficial com duas mudanças, ambas verificadas localmente contra a imagem:
#
# 1. Porta. O nginx da imagem fixa a 5000, mas o Render encaminha para a porta de PORT
#    (padrão 10000). O backend do Postiz também lê PORT, então PORT=10000 o faria ouvir em
#    10000 enquanto o proxy /api/ do nginx aponta para 3000 (502). Aqui o nginx passa a
#    ouvir em PORT e o backend volta para 3000.
# 2. Temporal. A imagem exige TEMPORAL_ADDRESS (host:porta). O Blueprint só entrega o host
#    interno do serviço temporal, então a porta 7233 é anexada aqui.
#
# Fixe a versão em vez de :latest quando o Postiz estiver estável em produção.
FROM ghcr.io/gitroomhq/postiz-app:latest

CMD ["sh", "-c", "sed -i \"s/listen 5000;/listen ${PORT:-10000};/\" /etc/nginx/nginx.conf && if [ -z \"$TEMPORAL_ADDRESS\" ] && [ -n \"$TEMPORAL_HOST\" ]; then export TEMPORAL_ADDRESS=\"$TEMPORAL_HOST:7233\"; fi && export PORT=3000 && nginx && pnpm run pm2"]
