import { Header, Notice, Panel, QueryState } from '../components/ui'
import { useApi } from '../lib/api'
import type { Configuration } from '../lib/types'

interface MethodologyData {
  algorithm_version: string
  formulas: { name: string; formula: string; description: string; origin: string }[]
  sources: { title: string; url: string; supports: string }[]
  configuration: Configuration
  example: { semantic: number; lexical: number; coverage: number; raw_score: number; gate: number; score: number }
  unrelated_example: { answer: string; question: string; semantic: number; raw_score: number; gate: number; score: number; note: string }
  steps: string[]
  relevance_policy: { semantic_floor: number; semantic_only_threshold: number; minimum_shared_terms: number; generic_terms: string[] }
  interpretation: string
  length_policy: string
}

export function Methodology() {
  const query = useApi<MethodologyData>('/analysis/methodology')
  const data = query.data
  return <>
    <Header title="Методика перевірки" eyebrow="ФОРМУЛИ ТА ДЖЕРЕЛА"
      subtitle="Як зіставляється зміст відповіді з кількома еталонами та формується рекомендація викладачу."/>
    <QueryState pending={query.isPending} error={query.error}/>
    {data && <>
      <Panel title={`Змістова перевірка · алгоритм ${data.algorithm_version}`}><div className="panel-body stack">
        <p>{data.length_policy}</p><p>{data.interpretation}</p>
        <p>Публікація питання потребує щонайменше двох різних еталонів. Непідтверджені варіації не беруть участі в аналізі.</p>
      </div></Panel>
      <Panel title="Як формується рекомендація"><div className="panel-body stack">
        <ol>{data.steps.map(step => <li key={step}>{step}</li>)}</ol>
        <p>Правило застосовується однаково до всіх питань і дисциплін, навіть якщо викладач не заповнив рубрику понять. Без рубрики використовуються предметні леми та семантика.</p>
      </div></Panel>
      {data.formulas.map(formula => <Panel key={formula.name} title={formula.name}><div className="panel-body stack">
        <code className="formula-line">{formula.formula}</code><p>{formula.description}</p><p className="muted">Походження: {formula.origin}</p>
      </div></Panel>)}
      <Panel title="Поточні ваги та приклад"><div className="panel-body stack">
        <p>Вага семантики a = {data.configuration.semantic_weight}; лексики b = {data.configuration.lexical_weight}; понять c = {data.configuration.concept_weight}.</p>
        <code className="formula-line">B = {data.configuration.semantic_weight} × {data.example.semantic} + {data.configuration.lexical_weight} × {data.example.lexical} + {data.configuration.concept_weight} × {data.example.coverage} = {data.example.raw_score}; G = 1; F = G × B = {data.example.score}</code>
        <p>Це арифметичний приклад. У кожній картці аналізу використано її власні збережені метрики й налаштування, а не ці демонстраційні числа.</p>
        <p>Перевірка зв’язку: S ≥ {data.relevance_policy.semantic_floor} і щонайменше одне знайдене поняття, {data.relevance_policy.minimum_shared_terms} спільні предметні леми або сильна семантика S ≥ {data.relevance_policy.semantic_only_threshold}. Критичне правило завжди обнуляє кандидата.</p>
        <p>Після перевірки зв’язку діють пороги категорій: нижній {data.configuration.low_threshold}, високий {data.configuration.high_threshold}. За G = 0 — завжди 0% і низька відповідність. За G = 1 і F нижче нижнього порогу — також низька відповідність. До високого порогу, за нового заперечення або пропущених обов’язкових понять — потребує перевірки. Решта — висока відповідність.</p>
        <Notice>Зважене покриття, поєднання метрик, ваги та пороги — інженерні рішення цього проєкту. Вони не запозичені як готова формула оцінки з SBERT і потребують перевірки на корпусі з розміткою викладачів.</Notice>
      </div></Panel>
      <Panel title="Чому стороння відповідь отримує 0%"><div className="panel-body stack">
        <p><strong>Питання:</strong> {data.unrelated_example.question}</p>
        <p><strong>Відповідь:</strong> {data.unrelated_example.answer}</p>
        <code className="formula-line">S = {data.unrelated_example.semantic}; L = 0; C = 0; B = {data.unrelated_example.raw_score}; G = 0; F = 0 × B = 0%</code>
        <p>{data.unrelated_example.note}</p>
        <p>Звичайні слова не є доказом знання теми. Повторення «система», «користувач», «відповідь» не замінює змістової відповіді. Для перевірки викладач бачить усі кандидати, початкову подібність і причину допуску або обнулення.</p>
        <details><summary>Загальні слова, які самі не підтверджують зв’язок</summary><p>{data.relevance_policy.generic_terms.join(', ')}</p></details>
      </div></Panel>
      <Panel title="Налаштування еталонів та історія"><div className="panel-body stack">
        <p>Додавайте повні альтернативні відповіді, поняття з синонімами та конкретні правила критичних помилок. Сильний змістовий перефраз без буквальних ключових слів може пройти перевірку зв’язку; нестача обов’язкових понять усе одно потребує рішення викладача.</p>
        <p>Версія алгоритму й усі параметри зберігаються з кожним аналізом. Попередні результати та рішення не стираються. Для старої версії доступна кнопка «Повторити аналіз».</p>
      </div></Panel>
      <Panel title="Наукові та технічні першоджерела"><div className="panel-body stack">
        {data.sources.map(source => <div key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><p>{source.supports}</p></div>)}
      </div></Panel>
    </>}
  </>
}
