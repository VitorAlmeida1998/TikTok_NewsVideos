import { Composition } from "remotion";
import { NewsShort, newsShortSchema, calculateNewsShortMetadata } from "./NewsShort";

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
          words: [],
        }}
        calculateMetadata={calculateNewsShortMetadata}
      />
    </>
  );
};
