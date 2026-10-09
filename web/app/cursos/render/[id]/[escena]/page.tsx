// Página que el backend fotografía con Chromium (course_render.capturar_escenas)
// para cada diapositiva del vídeo: solo la diapositiva a 1920×1080, sin menú
// ni el zoom de la interfaz. Componente de servidor: no necesita hidratar.

import SlideRender from "../../../components/SlideRender";
import type { Curso } from "../../../tipos";

export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

export default async function RenderEscena({ params }: { params: Promise<{ id: string; escena: string }> }) {
  const { id, escena: escenaId } = await params;
  const res = await fetch(`${BACKEND}/api/cursos/${id}`, { cache: "no-store" });
  if (!res.ok) return <p>Curso no encontrado</p>;
  const curso: Curso = await res.json();
  for (const m of curso.modulos) {
    for (const l of m.lecciones) {
      const i = l.escenas.findIndex((e) => e.id === escenaId);
      if (i < 0) continue;
      return (
        <>
          <link rel="stylesheet" precedence="default"
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono&display=swap" />
          <style>{`html{zoom:1 !important;background:#000} body{margin:0;min-height:0 !important} nav{display:none !important}
            nextjs-portal{display:none !important}`}</style>
          <div style={{ position: "fixed", top: 0, left: 0, zIndex: 100000 }}>
            <SlideRender escena={l.escenas[i]} tema={curso.tema} cursoId={curso.id}
              cursoTitulo={curso.titulo} numero={`${i + 1} / ${l.escenas.length}`} />
          </div>
        </>
      );
    }
  }
  return <p>Escena no encontrada</p>;
}
