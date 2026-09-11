import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile } from "remotion";
import { loadFont } from "@remotion/google-fonts/Montserrat";
import { z } from "zod";

const { fontFamily: montserrat } = loadFont("normal", {
  weights: ["700", "800", "900"],
  subsets: ["latin", "latin-ext"],
});
const FONT = `${montserrat}, "Segoe UI", Roboto, Arial, sans-serif`;

const ACCENT = "#ffcc00";
const INK = "#0f0c29";

// Capa (thumbnail) do vídeo: é o que aparece na grade do perfil e nos
// resultados de busca do TikTok. Diferente do NewsShort, aqui NADA anima —
// é um frame só, renderizado com `remotion still`. O frame escolhido do
// clipe de fundo é decidido do lado Python (video_gen/cover.py, ~25% da
// duração do clipe) e passado via --frame, pra nunca cair no logo/tela
// preta do começo do trailer.
//
// Campos extras do spec do vídeo (words, audioPath, ...) são ignorados:
// z.object() descarta chaves desconhecidas, então o MESMO JSON serve para
// as duas composições.
export const newsCoverSchema = z.object({
  itemId: z.number(),
  title: z.string(),
  source: z.string(),
  hook: z.string(),
  backgroundVideoPath: z.string().default(""),
  badge: z.string().default(""),
  gameName: z.string().default(""),
  // igual ao NewsShort: a marca vem do spec (data/settings.json)
  channelHandle: z.string().default("TikTok GameNews"),
});

export type NewsCoverProps = z.infer<typeof newsCoverSchema>;

// A capa é lida como miniatura (~200px de largura na grade do perfil), então
// o hook precisa ser o maior possível — mas NUNCA cortado: capa que corta a
// frase no meio perde justamente a palavra que faz a pessoa clicar. Escolhe
// o maior tamanho da lista que couber em HOOK_MAX_LINES linhas, estimando a
// largura média do caractere (Montserrat 900 é largo, e caixa alta mais
// ainda). A estimativa é conservadora e o line-clamp fica 1 linha acima como
// rede de segurança.
const HOOK_MAX_WIDTH = 960;
const HOOK_MAX_LINES = 4;
const HOOK_SIZES = [104, 92, 82, 74, 66, 58, 52];
const WRAP_SLACK = 1.12; // quebra de palavra desperdiça ~12% da linha

const hookFontSize = (hook: string): number => {
  const letters = hook.replace(/[^\p{L}]/gu, "");
  const upperRatio =
    letters.length > 0 ? letters.replace(/[^\p{Lu}]/gu, "").length / letters.length : 0;
  const charWidthRatio = upperRatio > 0.6 ? 0.7 : 0.62;
  const effectiveLength = hook.length * WRAP_SLACK;

  for (const size of HOOK_SIZES) {
    const perLine = Math.max(1, Math.floor(HOOK_MAX_WIDTH / (size * charWidthRatio)));
    if (Math.ceil(effectiveLength / perLine) <= HOOK_MAX_LINES) return size;
  }
  return HOOK_SIZES[HOOK_SIZES.length - 1];
};

const CoverBackground: React.FC<{ src: string }> = ({ src }) => (
  <AbsoluteFill>
    <OffthreadVideo
      src={src}
      muted
      style={{ width: "100%", height: "100%", objectFit: "cover" }}
    />
  </AbsoluteFill>
);

const CoverGradient: React.FC = () => (
  <AbsoluteFill
    style={{
      background: "linear-gradient(160deg, #0f0c29 0%, #302b63 50%, #24243e 100%)",
    }}
  >
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(circle at 32% 24%, rgba(255,204,0,0.18) 0%, rgba(255,204,0,0) 38%)",
      }}
    />
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(circle at 74% 74%, rgba(120,90,255,0.35) 0%, rgba(120,90,255,0) 42%)",
      }}
    />
  </AbsoluteFill>
);

// Mesmo tratamento do vídeo (escurece topo/base + vinheta), um pouco mais
// forte no topo porque aqui o texto é maior e precisa de mais contraste.
const ReadabilityOverlay: React.FC = () => (
  <>
    <AbsoluteFill style={{ background: "rgba(10, 8, 30, 0.22)" }} />
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(180deg, rgba(5,4,20,0.86) 0%, rgba(5,4,20,0.72) 34%, rgba(5,4,20,0.18) 58%, rgba(5,4,20,0.35) 80%, rgba(5,4,20,0.8) 100%)",
      }}
    />
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(ellipse at center, rgba(0,0,0,0) 50%, rgba(0,0,0,0.6) 100%)",
      }}
    />
  </>
);

export const NewsCover: React.FC<NewsCoverProps> = ({
  hook,
  badge,
  gameName,
  backgroundVideoPath,
  channelHandle,
}) => {
  const backgroundSrc = backgroundVideoPath ? staticFile(backgroundVideoPath) : "";

  return (
    <AbsoluteFill style={{ background: INK }}>
      {backgroundSrc ? <CoverBackground src={backgroundSrc} /> : <CoverGradient />}
      <ReadabilityOverlay />

      <AbsoluteFill
        style={{
          justifyContent: "flex-start",
          alignItems: "center",
          paddingTop: 210,
          paddingLeft: 60,
          paddingRight: 60,
        }}
      >
        {badge ? (
          <div
            style={{
              fontFamily: FONT,
              fontSize: 42,
              color: INK,
              background: ACCENT,
              padding: "14px 34px",
              borderRadius: 14,
              fontWeight: 900,
              letterSpacing: 2,
              boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
              transform: "rotate(-3deg)",
              marginBottom: 46,
            }}
          >
            {badge}
          </div>
        ) : null}

        <div
          style={{
            fontFamily: FONT,
            fontSize: hookFontSize(hook),
            lineHeight: 1.08,
            color: "white",
            fontWeight: 900,
            textAlign: "center",
            maxWidth: 960,
            textShadow: "0 8px 34px rgba(0,0,0,0.9), 0 2px 8px rgba(0,0,0,0.9)",
            display: "-webkit-box",
            // 1 linha acima do alvo de hookFontSize(): rede de segurança pra
            // estimativa errada, sem cortar a frase no caso normal.
            WebkitLineClamp: HOOK_MAX_LINES + 1,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {hook}
        </div>

        {gameName ? (
          <div
            style={{
              marginTop: 44,
              fontFamily: FONT,
              fontSize: 34,
              fontWeight: 800,
              letterSpacing: 1.5,
              textTransform: "uppercase",
              color: INK,
              background: "rgba(255,255,255,0.92)",
              padding: "12px 30px",
              borderRadius: 999,
              maxWidth: 900,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {gameName}
          </div>
        ) : null}
      </AbsoluteFill>

      <AbsoluteFill
        style={{
          justifyContent: "flex-end",
          alignItems: "flex-start",
          padding: "0 0 64px 60px",
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 32,
            color: "rgba(255,255,255,0.82)",
            fontWeight: 800,
            letterSpacing: 0.5,
            textShadow: "0 3px 12px rgba(0,0,0,0.8)",
          }}
        >
          {channelHandle}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
