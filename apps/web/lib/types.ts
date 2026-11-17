export type Project = {
  id: string;
  title: string;
  channel?: string | null;
  thumbnail_url?: string | null;
  source_type: string;
  source_url: string | null;
  status: string;
  stage: string;
  progress: number;
  error_message: string | null;
  duration_seconds: number | null;
  has_video: boolean;
  has_audio: boolean;
  frame_x?: number | null;
  frame_y?: number | null;
  frame_w?: number | null;
  frame_h?: number | null;
  created_at: string;
  jobs?: Job[];
};

export type Job = {
  id: string;
  kind: string;
  status: string;
  progress: number;
  message: string | null;
  error_message: string | null;
  clip_id: string | null;
};

export type Word = {
  word: string;
  start: number;
  end: number;
};

export type Clip = {
  id: string;
  project_id: string;
  project_title?: string;
  start_seconds: number;
  end_seconds: number;
  score: number;
  title: string;
  hook: string;
  reason: string;
  status: string;
  caption_text: string;
  font_name: string;
  font_size: number;
  primary_color: string;
  highlight_color: string;
  position: string;
  has_file: boolean;
  error_message: string | null;
};

export type Template = {
  id: string;
  name: string;
  font_name: string;
  font_size: number;
  primary_color: string;
  highlight_color: string;
  position: string;
};

export type Channel = {
  id: string;
  name: string;
  identifier: string;
  disabled: boolean;
  profile: string | null;
};
