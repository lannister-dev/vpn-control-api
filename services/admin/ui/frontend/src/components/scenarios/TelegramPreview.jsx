import { Icon } from "../Icon.jsx";
import { BUTTON_STYLES, stripTags } from "./scenarioModel.js";

const SAMPLE = { name: "Алексей", referral: "vpn.gg/r/ax93", plan: "Год", days_left: "2", balance: "150 ₽" };

function renderBody(html) {
  const s = (html || "").replace(/\{(\w+)\}/g, (m, k) => (SAMPLE[k] != null ? SAMPLE[k] : m));
  return { __html: s };
}

export function TelegramPreview({ node }) {
  const btns = node.buttons || [];
  const empty = !stripTags(node.text) && !node.media;
  return (
    <div className="tgp">
      <div className="tgp-bar">
        <span className="tgp-ava">V</span>
        <div>
          <div className="tgp-bot-name">VPN Bot</div>
          <div className="tgp-bot-sub">bot</div>
        </div>
      </div>
      <div className="tgp-chat">
        <div className="tgp-bubble">
          {node.media && (
            <div className="tgp-media">
              <Icon name="image" size={20} />
              {node.media.name}
            </div>
          )}
          {empty
            ? <span className="tgp-empty">Текст сообщения пуст…</span>
            : <div className="tgp-text" dangerouslySetInnerHTML={renderBody(node.text)} />}
          <div className="tgp-time">12:30</div>
        </div>
        {btns.length > 0 && (
          <div className="tgp-kb">
            {btns.map((b, i) => {
              const st = BUTTON_STYLES[b.style] || BUTTON_STYLES[""];
              return (
                <div className="tgp-kb-row" key={i}>
                  <span className={"tgp-key " + st.tg}>{b.text || "Кнопка"}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
