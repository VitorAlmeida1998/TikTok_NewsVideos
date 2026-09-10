import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
  CalculateMetadataFunction,
  Loop,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Montserrat";
import { z } from "zod";

const { fontFamily: montserrat } = loadFont("normal", {
  weights: ["700", "800", "900"],
  subsets: ["latin", "latin-ext"],
});
const FONT = `${montserrat}, "Segoe UI", Roboto, Arial, sans-serif`;

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
  backgroundVideoPath: z.string().default(""),
  musicPath: z.string().default(""),
  badge: z.string().default(""),
  // marca do canal: vem do spec (data/settings.json) pra trocar o nome sem
  // mexer em código; os defaults abaixo valem pra specs antigos
  channelHandle: z.string().default("TikTok GameNews"),
  channelInitials: z.string().default("GN"),
  words: z.array(wordSchema),
});

export type NewsShortProps = z.infer<typeof newsShortSchema>;
type Word = NewsShortProps["words"][number];

const FPS = 30;
const TAIL_SECONDS = 1.5; // segundos extras após a última palavra antes do vídeo acabar

const ACCENT = "#ffcc00";
const INK = "#0f0c29";

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

// ---------------------------------------------------------------- fundo

// Fundo gradiente animado (quando não há clipe de gameplay): dois "blobs"
// de luz derivam lentamente, pra tela nunca parecer estática.
const GradientBackground: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const x1 = 30 + Math.sin(t * 0.25) * 18;
  const y1 = 25 + Math.cos(t * 0.2) * 14;
  const x2 = 72 + Math.cos(t * 0.18) * 16;
  const y2 = 75 + Math.sin(t * 0.22) * 12;

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(160deg, #0f0c29 0%, #302b63 50%, #24243e 100%)",
      }}
    >
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${x1}% ${y1}%, rgba(255,204,0,0.18) 0%, rgba(255,204,0,0) 38%)`,
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${x2}% ${y2}%, rgba(120,90,255,0.35) 0%, rgba(120,90,255,0) 42%)`,
        }}
      />
    </AbsoluteFill>
  );
};

// Fundo de gameplay/trailer em loop com zoom lento (Ken Burns).
//
// Usa OffthreadVideo em vez de Video: o componente <Video> depende do
// elemento <video> do navegador para extrair cada frame durante o
// render, o que falha em "seekar" corretamente em clipes baixados via
// yt-dlp (frame rate variável/VFR), causando flicker/frames pretos
// piscando, principalmente perto do loop. OffthreadVideo extrai o frame
// exato via ffmpeg (fora da thread do navegador), evitando esse bug —
// é a recomendação oficial do Remotion para renderização (não preview).
//
// GAMEPLAY_CLIP_DURATION_SECONDS precisa bater com CLIP_DURATION_SECONDS
// em video_gen/gameplay.py — o clipe já vem longo (60s) para cobrir a
// narração inteira sem repetir; o <Loop> só entra em ação de fato para
// narrações excepcionalmente longas.
const GAMEPLAY_CLIP_DURATION_SECONDS = 60;

const GameplayBackground: React.FC<{ src: string }> = ({ src }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const clipFrames = Math.round(GAMEPLAY_CLIP_DURATION_SECONDS * fps);
  const scale = interpolate(frame, [0, durationInFrames], [1, 1.08], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ transform: `scale(${scale})` }}>
      <Loop durationInFrames={clipFrames} times={Math.ceil(durationInFrames / clipFrames)}>
        <OffthreadVideo
          src={src}
          muted
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </Loop>
    </AbsoluteFill>
  );
};

// Escurece topo (atrás do hook) e base (atrás das legendas), deixando o
// meio do clipe visível; vinheta suave nas bordas.
const ReadabilityOverlay: React.FC = () => (
  <>
    <AbsoluteFill style={{ background: "rgba(10, 8, 30, 0.18)" }} />
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(180deg, rgba(5,4,20,0.7) 0%, rgba(5,4,20,0.3) 22%, rgba(5,4,20,0) 36%, rgba(5,4,20,0) 56%, rgba(5,4,20,0.45) 74%, rgba(5,4,20,0.88) 100%)",
      }}
    />
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(ellipse at center, rgba(0,0,0,0) 52%, rgba(0,0,0,0.55) 100%)",
      }}
    />
  </>
);

// ---------------------------------------------------------------- hook

const HOOK_HOLD_SECONDS = 1.0;
const HOOK_EXIT_FRAMES = 12;

const HookOverlay: React.FC<{
  hook: string;
  source: string;
  hideAt: number; // segundos
}> = ({ hook, source, hideAt }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const hookWords = hook.split(/\s+/).filter(Boolean);
  const exitStart = Math.round(hideAt * fps);

  if (frame >= exitStart + HOOK_EXIT_FRAMES) return null;

  const exit = interpolate(frame, [exitStart, exitStart + HOOK_EXIT_FRAMES], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.in(Easing.cubic),
  });

  const pillEnter = spring({ frame, fps, config: { damping: 14, stiffness: 120 } });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "center",
        paddingTop: 168,
        opacity: 1 - exit,
        transform: `translateY(${-48 * exit}px)`,
      }}
    >
      <div
        style={{
          fontFamily: FONT,
          fontSize: 66,
          lineHeight: 1.12,
          color: "white",
          fontWeight: 900,
          textAlign: "center",
          maxWidth: 940,
          textShadow: "0 6px 28px rgba(0,0,0,0.75)",
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          columnGap: 18,
          rowGap: 4,
        }}
      >
        {hookWords.map((w, i) => {
          const s = spring({
            frame: frame - i * 3,
            fps,
            config: { damping: 12, stiffness: 160, mass: 0.6 },
          });
          return (
            <span
              key={`${w}-${i}`}
              style={{
                display: "inline-block",
                opacity: s,
                transform: `translateY(${(1 - s) * 34}px) scale(${0.8 + s * 0.2})`,
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
      <div
        style={{
          marginTop: 24,
          fontFamily: FONT,
          fontSize: 22,
          fontWeight: 800,
          letterSpacing: 2.5,
          textTransform: "uppercase",
          color: "rgba(255,255,255,0.9)",
          background: "rgba(255,255,255,0.12)",
          border: "1px solid rgba(255,255,255,0.22)",
          padding: "8px 20px",
          borderRadius: 999,
          opacity: pillEnter,
          transform: `scale(${0.9 + pillEnter * 0.1})`,
        }}
      >
        via {source}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- legendas

type Chunk = { words: Word[]; firstIndex: number; start: number; end: number };

const CHUNK_MAX_WORDS = 4;
const CHUNK_MAX_SECONDS = 1.8;
const SENTENCE_END = /[.!?…]["»)]?$/;
const CHUNK_LINGER_SECONDS = 0.6;

const buildChunks = (words: Word[]): Chunk[] => {
  const chunks: Chunk[] = [];
  let current: Word[] = [];
  let firstIndex = 0;

  const flush = () => {
    if (current.length === 0) return;
    chunks.push({
      words: current,
      firstIndex,
      start: current[0].start,
      end: current[current.length - 1].end,
    });
    current = [];
  };

  words.forEach((w, i) => {
    if (current.length === 0) firstIndex = i;
    current.push(w);
    const clean = w.word.trim();
    const sentenceEnd = SENTENCE_END.test(clean);
    const comma = /,$/.test(clean) && current.length >= 2;
    const tooLong = w.end - current[0].start >= CHUNK_MAX_SECONDS;
    if (sentenceEnd || comma || tooLong || current.length >= CHUNK_MAX_WORDS) {
      flush();
    }
  });
  flush();
  return chunks;
};

const WordCaptions: React.FC<{ words: Word[] }> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const chunks = useMemo(() => buildChunks(words), [words]);

  let chunk = chunks.find((c) => t >= c.start && t <= c.end);
  if (!chunk) {
    const previous = [...chunks].reverse().find((c) => c.end < t);
    if (previous && t - previous.end <= CHUNK_LINGER_SECONDS) chunk = previous;
  }
  if (!chunk) return null;

  const chunkFrame = frame - Math.round(chunk.start * fps);
  const enter = spring({
    frame: chunkFrame,
    fps,
    config: { damping: 13, stiffness: 190, mass: 0.7 },
  });

  const activeIndex = chunk.words.findIndex((w) => t >= w.start && t <= w.end);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 300,
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "center",
          columnGap: 28,
          rowGap: 10,
          maxWidth: 940,
          padding: "20px 36px",
          borderRadius: 26,
          background: "rgba(5, 4, 20, 0.6)",
          opacity: Math.min(1, enter * 2.5),
          transform: `translateY(${(1 - enter) * 24}px) scale(${0.92 + enter * 0.08})`,
        }}
      >
        {chunk.words.map((w, i) => {
          const isActive = i === activeIndex;
          const wordFrame = frame - Math.round(w.start * fps);
          const pop = isActive
            ? spring({
                frame: wordFrame,
                fps,
                config: { damping: 9, stiffness: 260, mass: 0.5 },
              })
            : 0;
          const scale = 1 + pop * 0.1;
          return (
            <span
              key={`${w.word}-${chunk.firstIndex + i}`}
              style={{
                display: "inline-block",
                padding: "0 4px",
                fontFamily: FONT,
                fontSize: 58,
                fontWeight: 900,
                lineHeight: 1.15,
                textTransform: "uppercase",
                letterSpacing: 0.5,
                color: isActive ? ACCENT : "white",
                textShadow: isActive
                  ? "0 0 22px rgba(255,204,0,0.55), 0 4px 14px rgba(0,0,0,0.8)"
                  : "0 4px 14px rgba(0,0,0,0.8)",
                transform: `scale(${scale})`,
                transformOrigin: "center",
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

// ---------------------------------------------------------------- selo / CTA / marca

// Nome/handle do canal: vem das props (data/settings.json via spec), sempre
// visível num canto discreto — reconhecimento de marca (quem rola o feed passa
// a reconhecer o canal) e proteção contra reupload sem crédito.

// Card "segue o perfil" na lateral direita (faixa livre entre o hook/CTA no
// topo e as legendas embaixo). Aparece duas vezes: um lembrete curto no meio
// do vídeo e de novo junto com o CTA final, até o fim.
const SHOW_FOLLOW_NUDGE = true;
const NUDGE_MID_AT = 0.35; // fração da duração em que o lembrete do meio entra
const NUDGE_MID_SECONDS = 2.2;
const NUDGE_MIN_VIDEO_SECONDS = 12; // vídeos mais curtos só mostram junto do CTA
const NUDGE_EXIT_FRAMES = 10;
const NUDGE_RED = "#ff2d55";

const FollowNudge: React.FC<{ ctaShowAfter: number; initials: string }> = ({
  ctaShowAfter,
  initials,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const t = frame / fps;
  const duration = durationInFrames / fps;

  const midStart = duration * NUDGE_MID_AT;
  const midEnd = midStart + NUDGE_MID_SECONDS;
  const midAllowed = duration >= NUDGE_MIN_VIDEO_SECONDS && midEnd < ctaShowAfter - 0.5;

  let windowStart: number | null = null;
  let windowEnd: number | null = null; // null = fica até o fim
  if (t >= ctaShowAfter) {
    windowStart = ctaShowAfter;
  } else if (midAllowed && t >= midStart && t < midEnd) {
    windowStart = midStart;
    windowEnd = midEnd;
  }
  if (windowStart === null) return null;

  const localFrame = frame - Math.round(windowStart * fps);
  const enter = spring({
    frame: localFrame,
    fps,
    config: { damping: 11, stiffness: 170, mass: 0.7 },
  });
  const exit =
    windowEnd === null
      ? 0
      : interpolate(
          frame,
          [Math.round(windowEnd * fps) - NUDGE_EXIT_FRAMES, Math.round(windowEnd * fps)],
          [0, 1],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.in(Easing.cubic) },
        );
  const pulse = windowEnd === null ? 1 + Math.sin((localFrame / fps) * Math.PI * 1.6) * 0.03 : 1;

  // "+" quica a cada ~1.2s
  const cycle = localFrame % Math.round(1.2 * fps);
  const bounce = spring({ frame: cycle, fps, config: { damping: 7, stiffness: 220, mass: 0.5 } });
  const plusY = -14 * (1 - bounce);

  const chevronX = Math.sin((localFrame / fps) * Math.PI * 2.5) * 6;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "flex-end",
        paddingTop: 800,
        paddingRight: 40,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          width: 300,
          padding: "14px 16px 14px 14px",
          borderRadius: 999,
          background: "rgba(5, 4, 20, 0.72)",
          backdropFilter: "blur(6px)",
          boxShadow: "0 10px 30px rgba(0,0,0,0.45)",
          opacity: enter * (1 - exit),
          transform: `translateX(${(1 - enter) * 120 + exit * 80}px) scale(${(0.85 + enter * 0.15) * pulse})`,
          transformOrigin: "right center",
        }}
      >
        <div style={{ position: "relative", width: 92, height: 92, flexShrink: 0 }}>
          <div
            style={{
              width: 92,
              height: 92,
              borderRadius: "50%",
              background: ACCENT,
              border: "4px solid white",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: FONT,
              fontWeight: 900,
              fontSize: 36,
              color: INK,
              letterSpacing: 1,
            }}
          >
            {initials}
          </div>
          <div
            style={{
              position: "absolute",
              left: "50%",
              bottom: -16,
              width: 36,
              height: 36,
              borderRadius: "50%",
              background: NUDGE_RED,
              border: "3px solid white",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: FONT,
              fontWeight: 900,
              fontSize: 28,
              lineHeight: 1,
              color: "white",
              transform: `translate(-50%, ${plusY}px)`,
            }}
          >
            +
          </div>
        </div>
        <div
          style={{
            fontFamily: FONT,
            fontWeight: 800,
            fontSize: 25,
            lineHeight: 1.1,
            color: "white",
            textTransform: "uppercase",
            letterSpacing: 0.5,
            flex: 1,
          }}
        >
          Segue
          <br />
          o perfil
        </div>
        <div
          style={{
            fontFamily: FONT,
            fontWeight: 900,
            fontSize: 44,
            lineHeight: 1,
            color: ACCENT,
            transform: `translateX(${chevronX}px)`,
          }}
        >
          ›
        </div>
      </div>
    </AbsoluteFill>
  );
};

const BrandWatermark: React.FC<{ handle: string }> = ({ handle }) => (
  <AbsoluteFill
    style={{
      justifyContent: "flex-end",
      alignItems: "flex-start",
      padding: "0 0 40px 40px",
    }}
  >
    <div
      style={{
        fontFamily: FONT,
        fontSize: 22,
        color: "rgba(255,255,255,0.6)",
        fontWeight: 700,
        letterSpacing: 0.5,
        textShadow: "0 2px 8px rgba(0,0,0,0.6)",
      }}
    >
      {handle}
    </div>
  </AbsoluteFill>
);

// Selo de canto (ex: "VAZOU", "CONFIRMADO") derivado das keywords de
// relevância do item — reforça a promessa de "notícia quente, saiu agora" e
// dá ao canal um padrão visual reconhecível. Some quando o CTA final aparece,
// pra não competir visualmente com o pill do CTA.
const BadgeOverlay: React.FC<{ badge: string; hideAfter: number }> = ({
  badge,
  hideAfter,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!badge || frame >= hideAfter * fps) return null;

  const enter = spring({ frame, fps, config: { damping: 10, stiffness: 200, mass: 0.6 } });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "flex-start",
        padding: "56px 0 0 48px",
      }}
    >
      <div
        style={{
          fontFamily: FONT,
          fontSize: 28,
          color: INK,
          background: ACCENT,
          padding: "10px 22px",
          borderRadius: 10,
          fontWeight: 900,
          letterSpacing: 1.5,
          boxShadow: "0 8px 24px rgba(0,0,0,0.45)",
          opacity: enter,
          transform: `rotate(-3deg) scale(${0.6 + enter * 0.4})`,
          transformOrigin: "left center",
        }}
      >
        {badge}
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
  const localFrame = frame - Math.round(showAfter * fps);
  if (localFrame < 0) return null;

  const enter = spring({
    frame: localFrame,
    fps,
    config: { damping: 12, stiffness: 150, mass: 0.8 },
  });
  const pulse = 1 + Math.sin((localFrame / fps) * Math.PI * 1.6) * 0.02;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "center",
        paddingTop: 200,
        opacity: enter,
        transform: `translateY(${(1 - enter) * 70}px)`,
      }}
    >
      <div
        style={{
          fontFamily: FONT,
          fontSize: 38,
          lineHeight: 1.2,
          color: INK,
          background: ACCENT,
          padding: "18px 40px",
          borderRadius: 999,
          fontWeight: 900,
          textAlign: "center",
          maxWidth: 900,
          boxShadow: "0 10px 32px rgba(0,0,0,0.5)",
          transform: `scale(${pulse})`,
        }}
      >
        {cta}
      </div>
    </AbsoluteFill>
  );
};

const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames, width } = useVideoConfig();
  const w = interpolate(frame, [0, durationInFrames - 1], [0, width], {
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end" }}>
      <div style={{ height: 8, width: "100%", background: "rgba(255,255,255,0.12)" }}>
        <div style={{ height: "100%", width: w, background: ACCENT }} />
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- música

// Música de fundo (OST/tema do jogo) em loop, em volume baixo para não
// competir com a narração — a narração é sempre a prioridade de mixagem.
// MUSIC_CLIP_DURATION_SECONDS precisa bater com CLIP_DURATION_SECONDS em
// video_gen/music.py.
const MUSIC_CLIP_DURATION_SECONDS = 60;
const MUSIC_VOLUME = 0.12;
const MUSIC_FADE_IN_SECONDS = 0.8;
const MUSIC_FADE_OUT_SECONDS = 1.5;

const BackgroundMusic: React.FC<{ src: string }> = ({ src }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const clipFrames = Math.round(MUSIC_CLIP_DURATION_SECONDS * fps);
  // Volume calculado com o frame GLOBAL (fora do <Loop>, cujo frame é local
  // à iteração), pra o fade-out acontecer no fim do vídeo e não do loop.
  const volume = interpolate(
    frame,
    [
      0,
      MUSIC_FADE_IN_SECONDS * fps,
      durationInFrames - MUSIC_FADE_OUT_SECONDS * fps,
      durationInFrames,
    ],
    [0, MUSIC_VOLUME, MUSIC_VOLUME, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <Loop durationInFrames={clipFrames} times={Math.ceil(durationInFrames / clipFrames)}>
      <Audio src={src} volume={volume} />
    </Loop>
  );
};

// ---------------------------------------------------------------- composição

export const NewsShort: React.FC<NewsShortProps> = ({
  hook,
  cta,
  source,
  audioPath,
  backgroundVideoPath,
  musicPath,
  badge,
  channelHandle,
  channelInitials,
  words,
}) => {
  const lastWordEnd = words.length > 0 ? words[words.length - 1].end : 8;
  const ctaShowAfter = Math.max(2, lastWordEnd - 1.5);

  // O hook fica na tela enquanto está sendo narrado (as N primeiras palavras
  // da narração são o hook) + um respiro, depois sai pra liberar o topo.
  const hookWordCount = hook.split(/\s+/).filter(Boolean).length;
  const hookNarrationEnd =
    words.length >= hookWordCount && hookWordCount > 0
      ? words[hookWordCount - 1].end
      : Math.min(3.5, lastWordEnd);
  const hookHideAt = Math.min(hookNarrationEnd + HOOK_HOLD_SECONDS, ctaShowAfter - 0.5);

  // audioPath chega como um caminho relativo dentro de remotion/public/
  // (ex: "audio/item_1.mp3"), copiado pra lá pelo assembler.py antes do render.
  const audioSrc = audioPath ? staticFile(audioPath) : "";
  const backgroundSrc = backgroundVideoPath ? staticFile(backgroundVideoPath) : "";
  const musicSrc = musicPath ? staticFile(musicPath) : "";

  return (
    <AbsoluteFill style={{ background: INK }}>
      {backgroundSrc ? <GameplayBackground src={backgroundSrc} /> : <GradientBackground />}
      <ReadabilityOverlay />
      {audioSrc ? <Audio src={audioSrc} /> : null}
      {musicSrc ? <BackgroundMusic src={musicSrc} /> : null}
      <BrandWatermark handle={channelHandle} />
      <BadgeOverlay badge={badge} hideAfter={ctaShowAfter} />
      <HookOverlay hook={hook} source={source} hideAt={hookHideAt} />
      <WordCaptions words={words} />
      {SHOW_FOLLOW_NUDGE ? (
        <FollowNudge ctaShowAfter={ctaShowAfter} initials={channelInitials} />
      ) : null}
      <CtaOverlay cta={cta} showAfter={ctaShowAfter} />
      <ProgressBar />
    </AbsoluteFill>
  );
};
