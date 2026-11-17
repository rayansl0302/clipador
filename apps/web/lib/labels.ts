const projectStatus: Record<string, string> = {
  queued: "Na fila",
  running: "Processando",
  done: "Pronto",
  failed: "Falhou",
};

const stageNames: Record<string, string> = {
  ingest: "Baixando o vídeo",
  transcribe: "Transcrevendo",
  suggest: "Separando os cortes",
  ready: "Pronto para revisar",
  render: "Renderizando",
  frame: "Enquadrando",
};

const clipStatus: Record<string, string> = {
  suggested: "Para revisar",
  approved: "Aprovado",
  rejected: "Rejeitado",
  rendered: "MP4 pronto",
};

const jobKind: Record<string, string> = {
  ingest: "Ingestão",
  transcribe: "Transcrição",
  suggest: "Cortes",
  render: "Render",
  frame: "Enquadramento",
};

export function projectStatusLabel(status: string): string {
  return projectStatus[status] ?? status;
}

export function stageLabel(stage: string): string {
  return stageNames[stage] ?? stage;
}

export function clipStatusLabel(status: string): string {
  return clipStatus[status] ?? status;
}

export function jobKindLabel(kind: string): string {
  return jobKind[kind] ?? kind;
}
