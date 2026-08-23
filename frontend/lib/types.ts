export type Agent = {
  id: string;
  name: string;
  voice_persona: string;
  language: string;
  custom_variables: Record<string, unknown>;
  result_schema: Record<string, unknown>;
};
