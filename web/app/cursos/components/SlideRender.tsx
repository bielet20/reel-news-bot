// Pinta una diapositiva a 1920×1080. Es el ÚNICO renderizador: lo usa el
// editor (escalado, con edición en línea) y la página /cursos/render que el
// backend fotografía con Chromium para el vídeo. Sin hooks: funciona también
// como componente de servidor.

import type { Contenido, Escena, Tema } from "../tipos";
import { TEMA_DEFECTO, urlArchivo } from "../tipos";

export const SLIDE_W = 1920;
export const SLIDE_H = 1080;

type Editar = ((c: Contenido) => void) | undefined;

function Texto({
  valor, campo, contenido, editar, style, placeholder,
}: {
  valor: string | undefined;
  campo: (c: Contenido, v: string) => Contenido;
  contenido: Contenido;
  editar: Editar;
  style?: React.CSSProperties;
  placeholder?: string;
}) {
  if (!editar) return valor ? <div style={style}>{valor}</div> : null;
  return (
    <div
      contentEditable
      suppressContentEditableWarning
      data-placeholder={placeholder || "Escribe aquí"}
      className="slide-editable"
      onBlur={(e) => {
        const v = e.currentTarget.innerText.replace(/\n+$/, "");
        if (v !== (valor || "")) editar(campo(contenido, v));
      }}
      style={{ outline: "none", minWidth: 40, ...style }}
    >
      {valor || ""}
    </div>
  );
}

function Lista({
  items, clave, contenido, editar, tema, numerada, tam = 46,
}: {
  items: string[] | undefined;
  clave: "vinetas" | "pasos";
  contenido: Contenido;
  editar: Editar;
  tema: Tema;
  numerada?: boolean;
  tam?: number;
}) {
  const lista = items || [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: tam * 0.62 }}>
      {lista.map((t, i) => (
        <div key={i} style={{ display: "flex", gap: tam * 0.6, alignItems: "flex-start" }}>
          {numerada ? (
            <div style={{
              flexShrink: 0, width: tam * 1.5, height: tam * 1.5, borderRadius: "50%", background: tema.acento,
              color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
              fontWeight: 800, fontSize: tam * 0.8, marginTop: -tam * 0.12,
            }}>{i + 1}</div>
          ) : (
            <div style={{ flexShrink: 0, width: tam * 0.36, height: tam * 0.36, borderRadius: 4, background: tema.acento, marginTop: tam * 0.42 }} />
          )}
          <Texto
            valor={t} contenido={contenido} editar={editar}
            campo={(c, v) => {
              const nueva = [...(c[clave] || [])];
              if (v.trim()) nueva[i] = v; else nueva.splice(i, 1);
              return { ...c, [clave]: nueva };
            }}
            style={{ fontSize: tam, lineHeight: 1.3, flex: 1 }}
          />
        </div>
      ))}
    </div>
  );
}

export default function SlideRender({
  escena, tema: temaCurso, cursoId, cursoTitulo, numero, editar,
}: {
  escena: Escena;
  tema?: Tema;
  cursoId: string;
  cursoTitulo?: string;
  numero?: string;
  editar?: (c: Contenido) => void;
}) {
  const tema = { ...TEMA_DEFECTO, ...(temaCurso || {}) };
  const c = escena.contenido || {};
  const fuente = `${tema.fuente}, "Segoe UI", Roboto, "DejaVu Sans", Arial, sans-serif`;
  const img = urlArchivo(cursoId, c.imagen);
  const titulo = (tam = 76, extra?: React.CSSProperties) => (
    <Texto valor={c.titulo} contenido={c} editar={editar} placeholder="Título"
      campo={(x, v) => ({ ...x, titulo: v })}
      style={{ fontSize: tam, fontWeight: 800, lineHeight: 1.12, letterSpacing: "-0.01em", ...extra }} />
  );
  const barra = <div style={{ width: 120, height: 10, borderRadius: 5, background: tema.acento, marginBottom: 36 }} />;
  const pad = { padding: "110px 130px" };

  let cuerpo: React.ReactNode;
  switch (escena.layout) {
    case "portada":
      cuerpo = (
        <div style={{ ...pad, height: "100%", display: "flex", flexDirection: "column", justifyContent: "center",
          background: `radial-gradient(circle at 85% 20%, ${tema.acento}55, transparent 55%)` }}>
          {cursoTitulo && <div style={{ fontSize: 34, color: tema.acento, fontWeight: 700, marginBottom: 28, textTransform: "uppercase", letterSpacing: "0.12em" }}>{cursoTitulo}</div>}
          {titulo(112)}
          <div style={{ width: 180, height: 12, borderRadius: 6, background: tema.acento, margin: "44px 0" }} />
          <Texto valor={c.subtitulo} contenido={c} editar={editar} placeholder="Subtítulo"
            campo={(x, v) => ({ ...x, subtitulo: v })} style={{ fontSize: 48, opacity: 0.8, lineHeight: 1.3 }} />
        </div>
      );
      break;
    case "imagen_texto":
      cuerpo = (
        <div style={{ height: "100%", display: "grid", gridTemplateColumns: "1fr 1fr" }}>
          <div style={{ ...pad, paddingRight: 80, display: "flex", flexDirection: "column", justifyContent: "center" }}>
            {barra}{titulo(68)}
            <div style={{ marginTop: 50 }}><Lista items={c.vinetas} clave="vinetas" contenido={c} editar={editar} tema={tema} tam={40} /></div>
          </div>
          <div style={{ background: `${tema.acento}22`, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
            {img ? (/* eslint-disable-next-line @next/next/no-img-element */
              <img src={img} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            ) : <div style={{ fontSize: 36, opacity: 0.5 }}>Sin imagen</div>}
          </div>
        </div>
      );
      break;
    case "imagen_completa":
      cuerpo = (
        <div style={{ position: "relative", height: "100%" }}>
          {img && (/* eslint-disable-next-line @next/next/no-img-element */
            <img src={img} alt="" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }} />
          )}
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.1) 45%, transparent 70%)" }} />
          <div style={{ position: "absolute", left: 130, right: 130, bottom: 110, color: "#fff" }}>{titulo(80)}</div>
        </div>
      );
      break;
    case "codigo":
      cuerpo = (
        <div style={{ ...pad, height: "100%", display: "flex", flexDirection: "column" }}>
          {barra}{titulo(64)}
          <div style={{ marginTop: 44, flex: 1, background: "#0b1020", border: `2px solid ${tema.acento}55`, borderRadius: 24, padding: "44px 52px", overflow: "hidden" }}>
            {c.lenguaje && <div style={{ fontSize: 26, color: tema.acento, marginBottom: 18, fontFamily: "monospace" }}>{c.lenguaje}</div>}
            <Texto valor={c.codigo} contenido={c} editar={editar} placeholder="código"
              campo={(x, v) => ({ ...x, codigo: v })}
              style={{ fontFamily: '"JetBrains Mono", "DejaVu Sans Mono", Consolas, monospace', fontSize: 36, lineHeight: 1.5, color: "#e2e8f0", whiteSpace: "pre-wrap" }} />
          </div>
        </div>
      );
      break;
    case "cita":
      cuerpo = (
        <div style={{ ...pad, height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", paddingLeft: 200, paddingRight: 200 }}>
          <div style={{ fontSize: 220, lineHeight: 0.6, color: tema.acento, fontFamily: "Georgia, serif" }}>“</div>
          <Texto valor={c.cita} contenido={c} editar={editar} placeholder="Cita"
            campo={(x, v) => ({ ...x, cita: v })} style={{ fontSize: 66, lineHeight: 1.3, fontStyle: "italic", fontWeight: 600 }} />
          <Texto valor={c.autor} contenido={c} editar={editar} placeholder="Autor"
            campo={(x, v) => ({ ...x, autor: v })} style={{ fontSize: 38, marginTop: 44, color: tema.acento }} />
        </div>
      );
      break;
    case "comparacion": {
      const cols = c.columnas?.length ? c.columnas : [{ titulo: "", vinetas: [] }, { titulo: "", vinetas: [] }];
      cuerpo = (
        <div style={{ ...pad, height: "100%", display: "flex", flexDirection: "column" }}>
          {barra}{titulo(64)}
          <div style={{ marginTop: 56, flex: 1, display: "grid", gridTemplateColumns: `repeat(${cols.length}, 1fr)`, gap: 48 }}>
            {cols.map((col, i) => (
              <div key={i} style={{ background: `${tema.acento}18`, border: `2px solid ${tema.acento}55`, borderRadius: 28, padding: "44px 48px" }}>
                <Texto valor={col.titulo} contenido={c} editar={editar} placeholder="Columna"
                  campo={(x, v) => { const n = [...cols]; n[i] = { ...n[i], titulo: v }; return { ...x, columnas: n }; }}
                  style={{ fontSize: 46, fontWeight: 800, color: tema.acento, marginBottom: 32 }} />
                <Lista items={col.vinetas} clave="vinetas" tema={tema} tam={36}
                  contenido={{ ...c, vinetas: col.vinetas }}
                  editar={editar ? (x) => { const n = [...cols]; n[i] = { ...n[i], vinetas: x.vinetas }; editar({ ...c, columnas: n }); } : undefined} />
              </div>
            ))}
          </div>
        </div>
      );
      break;
    }
    case "pasos":
      cuerpo = (
        <div style={{ ...pad, height: "100%", display: "flex", flexDirection: "column" }}>
          {barra}{titulo(64)}
          <div style={{ marginTop: 56 }}><Lista items={c.pasos} clave="pasos" contenido={c} editar={editar} tema={tema} numerada tam={42} /></div>
        </div>
      );
      break;
    case "cuestionario": {
      const ops = c.opciones || [];
      cuerpo = (
        <div style={{ ...pad, height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ fontSize: 34, color: tema.acento, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 30 }}>Pon a prueba lo aprendido</div>
          <Texto valor={c.pregunta} contenido={c} editar={editar} placeholder="Pregunta"
            campo={(x, v) => ({ ...x, pregunta: v })} style={{ fontSize: 66, fontWeight: 800, lineHeight: 1.2 }} />
          <div style={{ marginTop: 60, display: "flex", flexDirection: "column", gap: 26 }}>
            {ops.map((o, i) => (
              <div key={i} style={{ display: "flex", gap: 28, alignItems: "center", fontSize: 44, border: `2px solid ${tema.acento}55`, borderRadius: 20, padding: "22px 34px" }}>
                <span style={{ fontWeight: 800, color: tema.acento }}>{String.fromCharCode(65 + i)}</span>
                <Texto valor={o} contenido={c} editar={editar}
                  campo={(x, v) => { const n = [...ops]; n[i] = v; return { ...x, opciones: n }; }} />
              </div>
            ))}
          </div>
        </div>
      );
      break;
    }
    default: // vinetas, resumen
      cuerpo = (
        <div style={{ ...pad, height: "100%", display: "flex", flexDirection: "column" }}>
          {escena.layout === "resumen" && <div style={{ fontSize: 32, color: tema.acento, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 18 }}>Resumen</div>}
          {barra}{titulo(72)}
          <div style={{ marginTop: 60 }}><Lista items={c.vinetas} clave="vinetas" contenido={c} editar={editar} tema={tema} tam={48} /></div>
        </div>
      );
  }

  return (
    <div
      id="slide"
      data-listo="1"
      style={{
        width: SLIDE_W, height: SLIDE_H, position: "relative", overflow: "hidden",
        background: tema.fondo, color: tema.texto, fontFamily: fuente, boxSizing: "border-box",
      }}
    >
      {cuerpo}
      {(cursoTitulo || numero) && escena.layout !== "portada" && escena.layout !== "imagen_completa" && (
        <div style={{ position: "absolute", left: 130, right: 130, bottom: 44, display: "flex", justifyContent: "space-between", fontSize: 24, opacity: 0.45 }}>
          <span>{cursoTitulo}</span><span>{numero}</span>
        </div>
      )}
    </div>
  );
}
