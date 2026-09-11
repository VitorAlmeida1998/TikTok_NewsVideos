import { Composition } from "remotion";
import { NewsShort, newsShortSchema, calculateNewsShortMetadata } from "./NewsShort";
import { NewsCover, newsCoverSchema } from "./NewsCover";

const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="NewsShort"
        component={NewsShort}
        durationInFrames={30 * FPS}
        fps={FPS}
        width={1080}
        height={1920}
        schema={newsShortSchema}
        defaultProps={{
          itemId: 0,
          title: "Título de exemplo",
          source: "sample",
          hook: "Você não vai acreditar nessa notícia!",
          body: "Aqui vai o fato principal da notícia, resumido e direto ao ponto.",
          cta: "Comenta aqui o que você acha!",
          audioPath: "",
          backgroundVideoPath: "",
          musicPath: "",
          badge: "VAZOU",
          channelHandle: "TikTok GameNews",
          channelInitials: "GN",
          words: [],
        }}
        calculateMetadata={calculateNewsShortMetadata}
      />
      {/* Capa (thumbnail) do vídeo, renderizada com `remotion still`. Não é
          <Still> de propósito: precisamos renderizar um frame ADIANTADO do
          clipe de fundo (via --frame), e <Still> trava a duração em 1 frame.
          A duração aqui é a do clipe de fundo mais longo possível (60s). */}
      <Composition
        id="NewsCover"
        component={NewsCover}
        durationInFrames={60 * FPS}
        fps={FPS}
        width={1080}
        height={1920}
        schema={newsCoverSchema}
        defaultProps={{
          itemId: 0,
          title: "Título de exemplo",
          source: "sample",
          hook: "Você não vai acreditar nessa notícia!",
          backgroundVideoPath: "",
          badge: "VAZOU",
          // vazio de propósito: spec antigo sem gameName não pode cair num
          // placeholder e estampar "Nome do Jogo" na capa de verdade
          gameName: "",
          channelHandle: "TikTok GameNews",
        }}
      />
    </>
  );
};
