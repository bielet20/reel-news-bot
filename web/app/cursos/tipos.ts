// Tipos y utilidades de la zona «Cursos» (espejo de course_store.py).

export type Layout =
  | "portada" | "vinetas" | "imagen_texto" | "imagen_completa" | "codigo"
  | "cita" | "comparacion" | "pasos" | "resumen" | "cuestionario";

export interface Contenido {
  titulo?: string;
  subtitulo?: string;
  vinetas?: string[];
  imagen?: string;          // ruta relativa al curso (assets/...)
  imagen_prompt?: string;
  codigo?: string;
  lenguaje?: string;
  cita?: string;
  autor?: string;
  columnas?: { titulo?: string; vinetas?: string[] }[];
  pasos?: string[];
  pregunta?: string;
  opciones?: string[];
  correcta?: number;
}

export interface Escena {
  id: string;
  tipo: "diapositiva" | "video";
  layout: Layout;
  contenido: Contenido;
  narracion: string;
  notas: string;
  duracion: number | null;
  transicion: "fundido" | "corte";
  fuente: string;
  audio: { archivo: string; hash: string; duracion: number } | null;
  video: { archivo: string; inicio: number; fin: number; duracion_total?: number } | null;
}

export interface Leccion {
  id: string;
  titulo: string;
  resumen: string;
  objetivos: string[];
  estado: "pendiente" | "en_cola" | "generando" | "lista" | "error";
  error: string;
  escenas: Escena[];
  render: { archivo: string; srt: string; duracion: number; fecha: string } | null;
}

export interface Modulo { id: string; titulo: string; lecciones: Leccion[] }

export interface Tema { fondo: string; texto: string; acento: string; fuente: string }

export interface Documento {
  id: string; nombre: string; tipo: string; titulo: string;
  palabras: number; n_imagenes: number; n_diapositivas: number; url: string;
}

export interface Curso {
  id: string;
  titulo: string;
  descripcion: string;
  publico: string;
  tema: Tema;
  voz: { servicio: string; voz: string };
  musica: string | null;
  volumen_musica: number;
  subtitulos: boolean;
  duracion_leccion_min: number;
  documentos: Documento[];
  modulos: Modulo[];
  rev_modulos?: number;
  render?: { archivo: string; capitulos: string; duracion: number; fecha: string } | null;
}

export interface Tarea {
  id: string; curso_id: string; tipo: string; etiqueta: string; objetivo: string;
  estado: "en_cola" | "en_curso" | "completada" | "error"; log: string[]; error: string;
}

export const LAYOUTS: { id: Layout; label: string }[] = [
  { id: "portada", label: "Portada" },
  { id: "vinetas", label: "Título + viñetas" },
  { id: "imagen_texto", label: "Imagen + texto" },
  { id: "imagen_completa", label: "Imagen completa" },
  { id: "pasos", label: "Pasos" },
  { id: "comparacion", label: "Comparación" },
  { id: "codigo", label: "Código" },
  { id: "cita", label: "Cita" },
  { id: "resumen", label: "Resumen" },
  { id: "cuestionario", label: "Cuestionario" },
];

export const TEMA_DEFECTO: Tema = { fondo: "#0f172a", texto: "#f8fafc", acento: "#8b5cf6", fuente: "Inter" };

// Mismo ritmo y reglas que course_render.py
export const PALABRAS_POR_SEG = 2.3;
export const PAUSA_ESCENA = 0.7;
export const DURACION_SIN_VOZ = 5;

export function urlArchivo(cursoId: string, ruta?: string | null): string {
  return ruta ? `/api/cursos/${cursoId}/archivo/${ruta.split("/").map(encodeURIComponent).join("/")}` : "";
}

/** Duración estimada de la voz si aún no se ha generado. */
export function vozEstimada(e: Escena): number {
  const n = e.narracion.trim() ? e.narracion.trim().split(/\s+/).length : 0;
  return n / PALABRAS_POR_SEG;
}

/** Lo que dura la escena en el vídeo (misma regla que course_render.duracion_escena). */
export function duracionEscena(e: Escena): number {
  const voz = e.audio?.duracion ?? (e.narracion.trim() ? vozEstimada(e) : 0);
  if (e.tipo === "video" && e.video) {
    const clip = Math.max(0.5, (e.video.fin || 0) - (e.video.inicio || 0));
    return voz ? Math.max(clip, voz + 0.3) : clip; // voz más larga → se congela el último fotograma
  }
  if (e.duracion) return Math.max(e.duracion, voz ? voz + 0.2 : 0);
  return voz ? voz + PAUSA_ESCENA : DURACION_SIN_VOZ;
}

export function fmtDur(seg: number): string {
  const s = Math.round(seg);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}

export function nuevoId(): string {
  return Math.random().toString(16).slice(2, 12);
}

export function escenaVacia(layout: Layout = "vinetas"): Escena {
  return {
    id: nuevoId(), tipo: "diapositiva", layout,
    contenido: layout === "vinetas" ? { titulo: "Nueva diapositiva", vinetas: ["Primera idea"] } : { titulo: "Nueva diapositiva" },
    narracion: "", notas: "", duracion: null, transicion: "fundido", fuente: "", audio: null, video: null,
  };
}
