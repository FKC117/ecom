import { useEffect, useRef, useState } from 'react'
import { controlRequest, modelPath } from './api'
import ImageControl from './ImageControl'

function ErrorMessage({ error, labels }) {
  return error ? <p className="control-error" role="alert">{error.message || labels.error}</p> : null
}

function DataValue({ value, labels }) {
  if (typeof value === 'boolean') return <span className={`control-status-pill ${value ? 'positive' : ''}`}>{value ? labels.yes : labels.no}</span>
  return value === '' || value === null ? labels.blank : String(value)
}

function Records({ model, labels: l, navigate, onAuthError }) {
  const [data, setData] = useState(null)
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)
  const [revision, setRevision] = useState(0)
  const endpoint = modelPath(model)
  useEffect(() => {
    const controller = new AbortController()
    controlRequest(`${endpoint}?q=${encodeURIComponent(query)}&page=${page}`, {signal:controller.signal})
      .then((result) => { setData(result); setError(null) })
      .catch((failure) => { if (failure.name !== 'AbortError') {setError(failure); onAuthError(failure)} })
    return () => controller.abort()
  }, [endpoint, query, page, revision, onAuthError])
  return <>
    <div className="control-page-heading"><div><p className="eyebrow">{model.app_name}</p><h1>{model.name_plural}</h1><p>{data?.count ?? model.count} {l.records}</p></div><div className="control-toolbar">
      {model.can_export && <a className="control-button" href={`/api/control/${modelPath(model, 'export/')}`}>{l.export} ↓</a>}
      {model.import_url && <a className="control-button" href={model.import_url} target="_blank" rel="noreferrer" title={l.import_description}>{l.import} ↗</a>}
      {model.permissions.add && <button className="control-button primary" onClick={() => navigate(`/${model.key}/new`)}>＋ {l.add}</button>}
    </div></div>
    <section className="control-records-panel">
      <div className="control-list-tools">{model.searchable ? <form onSubmit={(event) => {event.preventDefault(); setQuery(new FormData(event.currentTarget).get('q') || ''); setPage(1)}}><label className="sr-only" htmlFor="record-search">{l.search}</label><input id="record-search" name="q" type="search" defaultValue={query} placeholder={l.search_placeholder} /><button className="control-button" type="submit">{l.search}</button></form> : <span className="control-muted">{l.records}</span>}<button className="control-button control-refresh" onClick={() => setRevision(revision + 1)} aria-label={l.refresh}>↻</button></div>
      <ErrorMessage error={error} labels={l} />
      {!data && !error && <p className="control-empty" role="status">{l.loading}</p>}
      {data && <><div className="control-table-wrap"><table className="control-table"><thead><tr>{data.columns.map((column) => <th key={column.key}>{column.label}</th>)}<th><span className="sr-only">{l.manage}</span></th></tr></thead><tbody>
        {data.rows.map((row) => <tr key={row.id}>{row.cells.map((cell,index) => <td key={data.columns[index].key} data-label={data.columns[index].label}>{index === 0 ? <button className="control-record-link" onClick={() => navigate(`/${model.key}/${encodeURIComponent(row.id)}`)}><DataValue value={cell} labels={l} /></button> : <DataValue value={cell} labels={l} />}</td>)}<td className="control-row-actions"><button className="control-button small" onClick={() => navigate(`/${model.key}/${encodeURIComponent(row.id)}`)}>{row.permissions.change ? l.edit : l.view} ↗</button></td></tr>)}
      </tbody></table></div>{!data.rows.length && <p className="control-empty">{l.empty}</p>}<div className="control-pagination"><span>{l.page} {data.page} / {data.pages}</span><div><button className="control-button small" disabled={page <= 1} onClick={() => setPage(page-1)}>← {l.previous}</button><button className="control-button small" disabled={page >= data.pages} onClick={() => setPage(page+1)}>{l.next} →</button></div></div></>}
    </section>
  </>
}

function RelatedSelect({ field, model, recordId, labels: l, disabled }) {
  const [choices, setChoices] = useState(field.choices)
  const [selected, setSelected] = useState(() => field.multiple ? (field.value || []).map(String) : String(field.value || ''))
  const [term, setTerm] = useState('')
  const [error, setError] = useState(null)
  const search = async () => {
    try {
      const result = await controlRequest(modelPath(model, `options/${encodeURIComponent(field.name)}/?q=${encodeURIComponent(term)}${recordId ? `&pk=${encodeURIComponent(recordId)}` : ''}`))
      const keep = choices.filter((choice) => field.multiple ? selected.includes(choice.value) : selected === choice.value)
      setChoices([...new Map([...keep, ...result.choices].map((choice) => [choice.value, choice])).values()])
      setError(null)
    } catch (failure) { setError(failure) }
  }
  return <><div className="control-relation-search"><input type="search" aria-label={`${l.search}: ${field.label}`} value={term} onChange={(event) => setTerm(event.target.value)} disabled={disabled} /><button className="control-button small" type="button" onClick={search} disabled={disabled}>{l.search}</button></div>{field.multiple ? <div className="control-multiple-choices" role="group" aria-label={field.label}>{choices.map((choice) => <label className="control-checkbox" key={choice.value}><input type="checkbox" name={field.name} value={choice.value} checked={selected.includes(choice.value)} disabled={disabled} onChange={(event) => setSelected(event.target.checked ? [...selected, choice.value] : selected.filter((value) => value !== choice.value))} /><span>{choice.label}</span></label>)}</div> : <select id={`field-${field.name}`} name={field.name} multiple={field.multiple} value={selected} onChange={(event) => setSelected(field.multiple ? Array.from(event.target.selectedOptions, (option) => option.value) : event.target.value)} required={field.required} disabled={disabled} size={field.multiple ? 6 : undefined}>{!field.multiple && <option value="">{l.select_empty}</option>}{choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select>}<ErrorMessage error={error} labels={l} /></>
}

function Field({ field: f, labels: l, model, recordId, editable, errors, onDirty }) {
  const disabled = !editable || f.disabled
  const attrs = { id:`field-${f.name}`, name:f.name, required:f.required, disabled, 'aria-invalid':!!errors?.length, 'aria-describedby':`help-${f.name}` }
  let input
  if (f.type === 'boolean') input = <label className="control-checkbox"><input {...attrs} type="checkbox" defaultChecked={f.value} required={false} /><span>{f.label}</span></label>
  else if (f.type === 'textarea' || f.type === 'json') input = <textarea {...attrs} defaultValue={f.value} rows={f.type === 'json' ? 14 : 4} spellCheck={f.type !== 'json'} className={f.type === 'json' ? 'control-json' : ''} />
  else if (f.type === 'select' && f.related) input = <RelatedSelect field={f} model={model} recordId={recordId} labels={l} disabled={disabled} />
  else if (f.type === 'select') input = <select {...attrs} multiple={f.multiple} defaultValue={f.multiple ? (f.value || []).map(String) : String(f.value ?? '')}>{!f.required && !f.choices.some((choice) => choice.value === '') && <option value="">{l.select_empty}</option>}{f.choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select>
  else if (f.type === 'file' && f.is_image) input = <ImageControl field={f} labels={l} model={model} recordId={recordId} attrs={attrs} editable={editable} onDirty={onDirty} />
  else if (f.type === 'file') input = <>{f.file_url && <div className="control-file-preview"><a href={f.file_url} target="_blank" rel="noreferrer">{l.current_file} ↗</a>{!f.required && editable && <label className="control-checkbox"><input type="checkbox" name={`${f.name}-clear`} /><span>{l.remove_file}</span></label>}</div>}<input {...attrs} type="file" required={f.required && !f.file_url} /></>
  else if (f.type === 'split_datetime') input = <div className="control-datetime"><input {...attrs} type="date" name={`${f.name}_0`} defaultValue={f.value[0]} aria-label={`${f.label}: ${l.date}`} /><input {...attrs} id={`field-${f.name}-time`} type="time" name={`${f.name}_1`} step="1" defaultValue={f.value[1]} aria-label={`${f.label}: ${l.time}`} /></div>
  else input = <input {...attrs} type={f.type === 'unsupported' ? 'text' : f.type} defaultValue={f.value} maxLength={f.max_length || undefined} min={f.min ?? undefined} max={f.max ?? undefined} step={f.type === 'number' ? f.step : undefined} autoComplete={f.type === 'password' ? 'new-password' : undefined} />
  return <div className={`control-field ${['textarea','json','file'].includes(f.type) ? 'wide' : ''}`}>{f.type !== 'boolean' && <label htmlFor={attrs.id}>{f.label}{f.required && <span className="control-required" aria-label={l.required}> *</span>}</label>}{input}<div id={`help-${f.name}`} className="control-field-help">{f.help}</div>{errors?.map((message,index) => <p role="alert" className="control-field-error" key={index}>{message}</p>)}</div>
}

function RelatedDeletion({ items }) {
  return <ul>{items.map((item,index) => <li key={index}>{Array.isArray(item) ? <RelatedDeletion items={item} /> : item}</li>)}</ul>
}

function DeleteDialog({ data, labels: l, onCancel, onConfirm, busy, error }) {
  const ref = useRef(null)
  useEffect(() => { ref.current.showModal() }, [])
  return <dialog ref={ref} className="dialog control-delete-dialog" aria-labelledby="delete-heading" onCancel={onCancel} onClose={onCancel}>
    <p className="eyebrow">{l.delete}</p><h2 id="delete-heading">{l.delete_title}</h2><p className="control-muted">{data.blocked ? l.delete_blocked : l.delete_description}</p><div className="control-deletion-tree"><RelatedDeletion items={data.related} /></div><ErrorMessage error={error} labels={l} /><div className="control-toolbar"><button className="control-button" onClick={onCancel} disabled={busy}>{l.cancel}</button><button className="control-button danger" onClick={onConfirm} disabled={busy || data.blocked}>{busy ? l.loading : l.delete_confirm}</button></div>
  </dialog>
}

function Editor({ model, recordId, initialQuery, labels: l, navigate, setDirty, onSaved, onAuthError }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [deletion, setDeletion] = useState(null)
  const endpoint = modelPath(model, `${recordId ? encodeURIComponent(recordId) : 'new'}/${!recordId && initialQuery ? `?${initialQuery}` : ''}`)
  useEffect(() => {
    const controller = new AbortController()
    controlRequest(endpoint, {signal:controller.signal}).then(setData).catch((failure) => { if (failure.name !== 'AbortError') {setError(failure); onAuthError(failure)} })
    return () => controller.abort()
  }, [endpoint, onAuthError])
  const parentValue = data?.fields.find((field) => field.name === model.parent_field)?.value
  const returnPath = model.parent_model && parentValue ? `/${model.parent_model}/${encodeURIComponent(parentValue)}` : model.parent_model ? `/${model.parent_model}` : model.permissions.view ? `/${model.key}` : ''
  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setFieldErrors({})
    try {
      const body = new FormData(event.currentTarget)
      const result = await controlRequest(endpoint, {method:'POST', body})
      const parent = model.parent_field && body.get(model.parent_field)
      await onSaved(result.message, parent ? `/${model.parent_model}/${encodeURIComponent(parent)}` : returnPath)
    } catch (failure) {setError(failure); setFieldErrors(failure.fields || {}); onAuthError(failure)}
    finally {setBusy(false)}
  }
  const prepareDelete = async () => {
    try {setDeletion(await controlRequest(modelPath(model, `${encodeURIComponent(recordId)}/delete/`))); setError(null)}
    catch (failure) {setError(failure); onAuthError(failure)}
  }
  const confirmDelete = async () => {
    setBusy(true)
    try {
      const form = new FormData(); form.set('confirm','yes')
      const result = await controlRequest(modelPath(model, `${encodeURIComponent(recordId)}/delete/`), {method:'POST',body:form})
      setDeletion(null)
      await onSaved(result.message, returnPath)
    } catch (failure) {setError(failure); onAuthError(failure)}
    finally {setBusy(false)}
  }
  if (!data) return <><button className="control-back" onClick={() => navigate(`/${model.key}`)}>← {l.back}</button><ErrorMessage error={error} labels={l} />{!error && <p className="control-empty" role="status">{l.loading}</p>}</>
  const editable = (recordId ? data.permissions.change : data.permissions.add) && !data.advanced
  return <>
    <button className="control-back" onClick={() => navigate(returnPath)}>← {l.back}</button>
    <div className="control-page-heading"><div><p className="eyebrow">{model.name_plural}</p><h1>{data.label || l.new_record}</h1>{!editable && <p>{l.view_only}</p>}</div>{recordId && data.permissions.delete && <button className="control-button danger-outline" onClick={prepareDelete} disabled={busy}>{l.delete}</button>}</div>
    <ErrorMessage error={error} labels={l} />{fieldErrors.__all__?.map((message,index) => <p key={index} className="control-error">{message}</p>)}
    {model.app === 'auth' && !editable && <p className="control-info">{l.access_management}</p>}
    {data.advanced && <div className="control-info">{l.advanced_form} <a href={data.django_url} target="_blank" rel="noreferrer">{l.open_django} ↗</a></div>}
    <form className="control-editor" onSubmit={submit} onChange={() => {if(editable) setDirty(true)}}>
      {data.groups.map((group,index) => <section className="control-form-section" key={index}>{group.title && <h2>{group.title}</h2>}<div className="control-field-grid">{group.fields.map((name) => {
        const field = data.fields.find((item) => item.name === name)
        const readonly = data.readonly.find((item) => item.name === name)
        return field ? <Field key={name} field={field} labels={l} model={model} recordId={recordId} editable={editable && !busy} errors={fieldErrors[name]} onDirty={()=>setDirty(true)} /> : readonly ? <div className="control-field" key={name}><label>{readonly.label}</label><p className="control-readonly"><DataValue value={readonly.value} labels={l} /></p><small className="control-muted">{l.read_only}</small></div> : null
      })}</div></section>)}
      {editable && <div className="control-savebar"><span className="control-muted">{model.name}</span><div className="control-toolbar"><button className="control-button" type="button" onClick={() => navigate(returnPath)} disabled={busy}>{l.cancel}</button><button className="control-button primary" type="submit" disabled={busy}>{busy ? l.loading : l.save} →</button></div></div>}
    </form>
    {data.related?.map((related) => <section className="control-form-section" key={related.key}><div className="control-section-title"><h2>{related.name}</h2>{related.can_add && <button type="button" className="control-button" onClick={() => navigate(`/${related.key}/new?${encodeURIComponent(related.field)}=${encodeURIComponent(recordId)}`)}>{l.add} →</button>}</div><div className="catalog-related-records">{related.records.map((record) => <button type="button" className="control-record-link" key={record.id} onClick={() => navigate(`/${related.key}/${encodeURIComponent(record.id)}`)}>{record.label} ↗</button>)}</div></section>)}
    {deletion && <DeleteDialog data={deletion} labels={l} onCancel={() => setDeletion(null)} onConfirm={confirmDelete} busy={busy} error={error} />}
  </>
}

export default function Workspace(props) {
  const [path, initialQuery = ''] = props.route.split('?')
  const parts = path.split('/').filter(Boolean)
  return parts.length > 1 ? <Editor {...props} initialQuery={initialQuery} recordId={parts[1] === 'new' ? null : decodeURIComponent(parts[1])} /> : <Records {...props} />
}
