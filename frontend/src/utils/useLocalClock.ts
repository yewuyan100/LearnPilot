import { useEffect, useMemo, useState } from "react";

const systemNow = () => new Date();

export function useLocalClock(getNow: () => Date = systemNow) {
  const [now, setNow] = useState(getNow);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(getNow()), 60_000);
    return () => window.clearInterval(timer);
  }, [getNow]);

  return useMemo(() => {
    const weekday = new Intl.DateTimeFormat("zh-CN", { weekday: "long" }).format(now);
    const hours = String(now.getHours()).padStart(2, "0");
    const minutes = String(now.getMinutes()).padStart(2, "0");
    return {
      dateLabel: `今天是 ${now.getMonth() + 1}月${now.getDate()}日 ${weekday}`,
      timeLabel: `${hours}:${minutes}`,
    };
  }, [now]);
}
