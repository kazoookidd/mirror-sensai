import { useNavigate } from "react-router-dom";
import { useApp } from "../../context/AppContext.jsx";

export function useAskSelection() {
  const { chooseScope } = useApp();
  const navigate = useNavigate();
  return async (sources) => {
    await chooseScope({ sources: [...sources] });
    navigate("/chat");
  };
}
