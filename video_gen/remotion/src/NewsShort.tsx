import React from "react";
import {
  AbsoluteFill,
  Audio,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
  CalculateMetadataFunction,
} from "remotion";
import { z } from "zod";

export const wordSchema = z.object({
  word: z.string(),
  start: z.number(),
  end: z.number(),
});

export const newsShortSchema = z.object({
  itemId: z.number(),
  title: z.string(),
  source: z.string(),
  hook: z.string(),
  body: z.string(),
  cta: z.string(),
  audioPath: z.string(),
  words: z.array(wordSchema),
});

export type NewsShortProps = z.infer<typeof newsShortSchema>;

const FPS = 30;
const TAIL_SECONDS = 1.5; // segundos extras após a última palavra antes do vídeo acabar

// Ajusta a duração total do vídeo dinamicamente com base no fim da última
// palavra transcrita (áudio real), em vez de um valor fixo arbitrário.
export const calculateNewsShortMetadata: CalculateMetadataFunction<
  NewsShortProps
> = ({ props }) => {
  const lastWordEnd =
    props.words.length > 0 ? props.words[props.words.length - 1].end : 8;
  const durationInSeconds = lastWordEnd + TAIL_SECONDS;
  return {
    durationInFrames: Math.ceil(durationInSeconds * FPS),
  };
};

const Background: React.FC = () => (
  <AbsoluteFill
    style={{
      background: "linear-gradient(160deg, #0f0c29 0%, #302b63 50%, #24243e 100%)",
    }}
  />
);

const HookOverlay: React.FC<{ hook: string; source: string }> = ({
  hook,
  source,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "center",
        paddingTop: 140,
        opacity: enter,
        transform: `translateY(${(1 - enter) * -30}px)`,
      }}
    >
      <div
        style={{
          fontSize: 28,
          color: "#ffcc00",
          fontFamily: "sans-serif",
          fontWeight: 700,
          letterSpacing: 2,
          textTransform: "uppercase",
          marginBottom: 20,
        }}
      >
        {source}
      </div>
      <div
        style={{
          fontSize: 64,
          color: "white",
          fontFamily: "sans-serif",
          fontWeight: 900,
          textAlign: "center",
          width: "85%",
          textShadow: "0 4px 20px rgba(0,0,0,0.6)",
          lineHeight: 1.15,
        }}
      >
        {hook}
      </div>
    </AbsoluteFill>
  );
};

// Legenda animada: mostra a palavra atual em destaque, estilo "karaokê",
// com base nos timestamps do faster-whisper.
const WordCaptions: React.FC<{ words: NewsShortProps["words"] }> = ({
  words,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const activeIndex = words.findIndex((w) => t >= w.start && t <= w.end);
  const windowSize = 4;
  const centerIndex = activeIndex === -1 ? 0 : activeIndex;
  const start = Math.max(0, centerIndex - 1);
  const visible = words.slice(start, start + windowSize);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 260,
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: 12,
          width: "88%",
        }}
      >
        {visible.map((w, i) => {
          const globalIndex = start + i;
          const isActive = globalIndex === activeIndex;
          return (
            <span
              key={`${w.word}-${globalIndex}`}
              style={{
                fontSize: 52,
                fontFamily: "sans-serif",
                fontWeight: 800,
                color: isActive ? "#ffcc00" : "white",
                textShadow: "0 3px 12px rgba(0,0,0,0.7)",
                transform: isActive ? "scale(1.12)" : "scale(1)",
                transformOrigin: "center",
                display: "inline-block",
                padding: "0 4px",
              }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const CtaOverlay: React.FC<{ cta: string; showAfter: number }> = ({
  cta,
  showAfter,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localFrame = frame - showAfter * fps;
  if (localFrame < 0) return null;

  const enter = interpolate(localFrame, [0, fps * 0.4], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "center",
        paddingTop: 40,
        opacity: enter,
      }}
    >
      <div
        style={{
          fontSize: 36,
          color: "#0f0c29",
          background: "#ffcc00",
          padding: "14px 28px",
          borderRadius: 999,
          fontFamily: "sans-serif",
          fontWeight: 800,
          textAlign: "center",
        }}
      >
        {cta}
      </div>
    </AbsoluteFill>
  );
};

export const NewsShort: React.FC<NewsShortProps> = ({
  hook,
  cta,
  source,
  audioPath,
  words,
}) => {
  const ctaShowAfter =
    words.length > 0 ? Math.max(2, words[words.length - 1].end - 1.5) : 4;

  // audioPath chega como um caminho relativo dentro de remotion/public/
  // (ex: "audio/item_1.mp3"), copiado pra lá pelo assembler.py antes do render.
  const audioSrc = audioPath ? staticFile(audioPath) : "";

  return (
    <AbsoluteFill>
      <Background />
      {audioSrc ? <Audio src={audioSrc} /> : null}
      <HookOverlay hook={hook} source={source} />
      <WordCaptions words={words} />
      <CtaOverlay cta={cta} showAfter={ctaShowAfter} />
    </AbsoluteFill>
  );
};
