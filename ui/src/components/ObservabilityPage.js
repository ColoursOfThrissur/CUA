import React, { useState, useEffect } from 'react';
import { Search, Filter, X, Eye, ChevronLeft, ChevronRight, RefreshCw, Copy, ArrowLeft } from 'lucide-react';
import { API_URL } from '../config';
import './ObservabilityPage.css';

const ObservabilityPage = ({ onBack }) => {
  const [tables, setTables] = useState([]);
  const [selectedTable, setSelectedTable] = useState(null);
  const [data, setData] = useState([]);
  const [columns, setColumns] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [limit] = useState(50);
  const [search, setSearch] = useState('');
  const [filterColumn, setFilterColumn] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [filterOptions, setFilterOptions] = useState([]);
  const [expandedRow, setExpandedRow] = useState(null);
  const [detailModal, setDetailModal] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchTables();
  }, []);

  useEffect(() => {
    if (selectedTable) {
      fetchData();
    }
  }, [selectedTable, page, search, filterColumn, filterValue]);

  const fetchTables = async () => {
    try {
      const res = await fetch(`${API_URL}/observability/tables`);
      const json = await res.json();
      setTables(json.tables || []);
      if (json.tables && json.tables.length > 0) {
        setSelectedTable(json.tables[0]);
      }
    } catch (err) {
      console.error('Failed to fetch tables:', err);
    }
  };

  const fetchData = async () => {
    if (!selectedTable) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: (page * limit).toString(),
      });
      if (search) params.append('search', search);
      if (filterColumn && filterValue) {
        params.append('filter_column', filterColumn);
        params.append('filter_value', filterValue);
      }

      const res = await fetch(
        `${API_URL}/observability/data/${selectedTable.db}/${selectedTable.table}?${params}`
      );
      const json = await res.json();
      setData(json.rows || []);
      setColumns(json.columns || []);
      setTotal(json.total || 0);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchFilterOptions = async (column) => {
    if (!selectedTable || !column) return;
    try {
      const res = await fetch(
        `${API_URL}/observability/filters/${selectedTable.db}/${selectedTable.table}/${column}`
      );
      const json = await res.json();
      setFilterOptions(json.values || []);
    } catch (err) {
      console.error('Failed to fetch filter options:', err);
    }
  };

  const handleTableSelect = (table) => {
    setSelectedTable(table);
    setPage(0);
    setSearch('');
    setFilterColumn('');
    setFilterValue('');
    setExpandedRow(null);
  };

  const handleFilterColumnChange = (column) => {
    setFilterColumn(column);
    setFilterValue('');
    if (column) {
      fetchFilterOptions(column);
    } else {
      setFilterOptions([]);
    }
  };

  const toggleRowExpand = (row) => {
    setDetailModal(row);
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
  };

  const formatValue = (value) => {
    if (value === null || value === undefined) return '-';
    if (typeof value === 'string' && value.length > 100) {
      return value.substring(0, 100) + '...';
    }
    return String(value);
  };

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="observability-page">
      <div className="obs-sidebar">
        <button className="obs-back-btn" onClick={onBack} title="Back to main">
          <ArrowLeft size={18} />
          Back
        </button>
        <h3>Tables</h3>
        <div className="table-list">
          {tables.map((table) => (
            <div
              key={`${table.db}-${table.table}`}
              className={`table-item ${selectedTable?.table === table.table ? 'active' : ''}`}
              onClick={() => handleTableSelect(table)}
            >
              <div className="table-label">{table.label}</div>
              <div className="table-name">{table.table}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="obs-content">
        {selectedTable && (
          <>
            <div className="obs-header">
              <h2>{selectedTable.label}</h2>
              <div className="obs-controls">
                <div className="search-box">
                  <Search size={18} />
                  <input
                    type="text"
                    placeholder="Search across all columns..."
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(0);
                    }}
                    className="search-input"
                  />
                </div>
                <div className="filter-box">
                  <Filter size={18} />
                  <select
                    value={filterColumn}
                    onChange={(e) => handleFilterColumnChange(e.target.value)}
                    className="filter-select"
                  >
                    <option value="">Filter by column...</option>
                    {columns.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                </div>
                {filterColumn && (
                  <select
                    value={filterValue}
                    onChange={(e) => {
                      setFilterValue(e.target.value);
                      setPage(0);
                    }}
                    className="filter-select"
                  >
                    <option value="">Select value...</option>
                    {filterOptions.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                )}
                <button
                  onClick={() => {
                    setSearch('');
                    setFilterColumn('');
                    setFilterValue('');
                    setPage(0);
                  }}
                  className="clear-btn"
                  title="Clear filters"
                >
                  <X size={16} />
                  Clear
                </button>
                <button
                  onClick={fetchData}
                  className="refresh-btn"
                  title="Refresh data"
                >
                  <RefreshCw size={16} />
                </button>
              </div>
            </div>

            <div className="obs-stats">
              Showing {page * limit + 1}-{Math.min((page + 1) * limit, total)} of {total} rows
            </div>

            {loading ? (
              <div className="loading">Loading...</div>
            ) : (
              <div className="obs-table-container">
                <table className="obs-table">
                  <thead>
                    <tr>
                      <th style={{ width: '40px' }}></th>
                      {columns.map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((row) => (
                      <React.Fragment key={row.id}>
                        <tr className="data-row">
                          <td>
                            <button
                              className="expand-btn"
                              onClick={() => toggleRowExpand(row)}
                              title="View details"
                            >
                              <Eye size={18} />
                            </button>
                          </td>
                          {columns.map((col) => (
                            <td key={col} title={row[col]}>
                              {formatValue(row[col])}
                            </td>
                          ))}
                        </tr>
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="obs-pagination">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="page-btn"
              >
                <ChevronLeft size={18} />
                Previous
              </button>
              <span className="page-info">
                Page {page + 1} of {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="page-btn"
              >
                Next
                <ChevronRight size={18} />
              </button>
            </div>
          </>
        )}

        {detailModal && (
          <div className="detail-modal-overlay" onClick={() => setDetailModal(null)}>
            <div className="detail-modal" onClick={(e) => e.stopPropagation()}>
              <div className="detail-modal-header">
                <h3>Row Details</h3>
                <button className="close-btn" onClick={() => setDetailModal(null)}>
                  <X size={20} />
                </button>
              </div>
              <div className="detail-modal-content">
                {columns.map((col) => (
                  <div key={col} className="detail-item">
                    <div className="detail-item-header">
                      <strong>{col}</strong>
                      <button 
                        className="detail-item-copy"
                        onClick={() => copyToClipboard(JSON.stringify(detailModal[col], null, 2))}
                        title="Copy to clipboard"
                      >
                        <Copy size={12} />
                        Copy
                      </button>
                    </div>
                    <pre>{JSON.stringify(detailModal[col], null, 2)}</pre>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ObservabilityPage;
