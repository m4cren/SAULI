export interface ApiUser {
  id: string;
  email: string | null;
  name: string | null;
  avatar_url: string | null;
}

export interface OllamaStatus {
  status: "connected";
  models: string[];
}
