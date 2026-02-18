/**
 * Watchlist - Customizable watchlist for tracking symbols
 */

import React, { useEffect } from 'react';
import { useWatchlists, useWatchlist, useCreateWatchlist, useDeleteWatchlist } from '../hooks/useWatchlist';
import { useWatchlistStore } from '../stores/watchlistStore';

export function Watchlist() {
  const { data: watchlistsData, isLoading: watchlistsLoading } = useWatchlists();
  const {
    selectedWatchlistId,
    setSelectedWatchlistId,
    selectedWatchlist,
    setSelectedWatchlist,
  } = useWatchlistStore();

  const { data: watchlistDetail, isLoading: detailLoading } = useWatchlist(selectedWatchlistId);
  const createMutation = useCreateWatchlist();
  const deleteMutation = useDeleteWatchlist();

  const watchlists = watchlistsData || [];

  // Select first watchlist by default
  useEffect(() => {
    if (watchlists.length > 0 && !selectedWatchlistId) {
      setSelectedWatchlistId(watchlists[0].id);
    }
  }, [watchlists, selectedWatchlistId, setSelectedWatchlistId]);

  // Update selected watchlist detail
  useEffect(() => {
    if (watchlistDetail) {
      setSelectedWatchlist(watchlistDetail);
    }
  }, [watchlistDetail, setSelectedWatchlist]);

  const handleCreateWatchlist = async () => {
    const name = prompt('Enter watchlist name:');
    if (name) {
      await createMutation.mutateAsync({ name });
    }
  };

  const handleDeleteWatchlist = async (id: number) => {
    if (confirm('Are you sure you want to delete this watchlist?')) {
      await deleteMutation.mutateAsync(id);
      if (selectedWatchlistId === id) {
        setSelectedWatchlistId(null);
      }
    }
  };

  if (watchlistsLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-zinc-400">Loading watchlists...</div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-[#0a0a0f] text-zinc-200 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
        <h1 className="text-xl font-bold">Watchlists</h1>
        <button
          onClick={handleCreateWatchlist}
          className="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 rounded"
        >
          + New Watchlist
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar - Watchlist selector */}
        <div className="w-48 border-r border-zinc-800 overflow-y-auto">
          {watchlists.map((list) => (
            <div
              key={list.id}
              onClick={() => setSelectedWatchlistId(list.id)}
              className={`px-4 py-3 cursor-pointer border-b border-zinc-800 hover:bg-zinc-900 ${
                selectedWatchlistId === list.id ? 'bg-zinc-900 border-l-2 border-l-blue-500' : ''
              }`}
            >
              <div className="text-sm font-medium">{list.name}</div>
              {list.description && (
                <div className="text-xs text-zinc-500 mt-1 truncate">{list.description}</div>
              )}
            </div>
          ))}
        </div>

        {/* Main content */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {selectedWatchlist ? (
            <>
              {/* Watchlist header */}
              <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">{selectedWatchlist.watchlist.name}</h2>
                  {selectedWatchlist.watchlist.description && (
                    <p className="text-xs text-zinc-500 mt-1">
                      {selectedWatchlist.watchlist.description}
                    </p>
                  )}
                </div>
                <div className="flex space-x-2">
                  <button
                    className="px-3 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 rounded"
                  >
                    + Add Symbol
                  </button>
                  <button
                    onClick={() => handleDeleteWatchlist(selectedWatchlist.watchlist.id)}
                    className="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 rounded"
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* Items table */}
              <div className="flex-1 overflow-y-auto">
                {selectedWatchlist.items.length === 0 ? (
                  <div className="p-8 text-center text-zinc-500">
                    <div className="mb-2">This watchlist is empty</div>
                    <div className="text-xs">Click "Add Symbol" to add trading pairs</div>
                  </div>
                ) : (
                  <table className="w-full text-xs">
                    <thead className="bg-zinc-900 sticky top-0">
                      <tr>
                        <th className="px-4 py-2 text-left text-zinc-400">Symbol</th>
                        <th className="px-4 py-2 text-left text-zinc-400">Exchange</th>
                        <th className="px-4 py-2 text-left text-zinc-400">Notes</th>
                        <th className="px-4 py-2 text-right text-zinc-400">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedWatchlist.items.map((item) => (
                        <tr key={item.id} className="border-b border-zinc-800 hover:bg-zinc-900">
                          <td className="px-4 py-3 font-mono font-bold">{item.symbol}</td>
                          <td className="px-4 py-3 text-zinc-400">{item.exchange}</td>
                          <td className="px-4 py-3 text-zinc-500">{item.notes || '-'}</td>
                          <td className="px-4 py-3 text-right">
                            <button className="text-red-400 hover:text-red-300 text-xs">
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-zinc-500">
              Select a watchlist or create a new one
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
