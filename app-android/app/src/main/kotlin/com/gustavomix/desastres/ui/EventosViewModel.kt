package com.gustavomix.desastres.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.gustavomix.desastres.core.EvaluadorDeFrescura
import com.gustavomix.desastres.core.Evento
import com.gustavomix.desastres.core.Filtro
import com.gustavomix.desastres.core.Frescura
import com.gustavomix.desastres.core.NivelAlerta
import com.gustavomix.desastres.core.TipoEvento
import com.gustavomix.desastres.core.conteoPorTipo
import com.gustavomix.desastres.core.filtrar
import com.gustavomix.desastres.core.paisesDisponibles
import com.gustavomix.desastres.data.RepositorioEventos
import java.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class EstadoPantalla(
    val cargando: Boolean = true,
    val error: String? = null,
    val filtro: Filtro = Filtro(),
    val frescura: Frescura = Frescura.Desconocida,
    /** Ya filtrados y ordenados: la pantalla no vuelve a decidir nada. */
    val eventos: List<Evento> = emptyList(),
    val paisesDisponibles: List<String> = emptyList(),
    val conteoPorTipo: Map<TipoEvento, Int> = emptyMap(),
    val totalSinFiltrar: Int = 0,
) {
    val vacioPorFiltros: Boolean
        get() = !cargando && error == null && eventos.isEmpty() && totalSinFiltrar > 0
}

class EventosViewModel(
    private val repositorio: RepositorioEventos,
    private val evaluador: EvaluadorDeFrescura = EvaluadorDeFrescura(),
    private val reloj: () -> Instant = Instant::now,
) : ViewModel() {

    private var todos: List<Evento> = emptyList()

    private val _estado = MutableStateFlow(EstadoPantalla())
    val estado: StateFlow<EstadoPantalla> = _estado.asStateFlow()

    init {
        refrescar()
    }

    fun refrescar() {
        _estado.update { it.copy(cargando = true, error = null) }

        viewModelScope.launch {
            repositorio.cargar()
                .onSuccess { feed ->
                    todos = feed.eventos
                    val frescura = evaluador.evaluar(feed, reloj())
                    _estado.update { previo ->
                        previo.copy(
                            cargando = false,
                            error = null,
                            frescura = frescura,
                            paisesDisponibles = todos.paisesDisponibles(),
                            conteoPorTipo = todos.conteoPorTipo(),
                            totalSinFiltrar = todos.size,
                        )
                    }
                    aplicarFiltro(_estado.value.filtro)
                }
                .onFailure { error ->
                    _estado.update {
                        it.copy(
                            cargando = false,
                            error = error.message ?: "No se pudieron cargar los datos",
                        )
                    }
                }
        }
    }

    fun aplicarFiltro(filtro: Filtro) {
        _estado.update { it.copy(filtro = filtro, eventos = todos.filtrar(filtro)) }
    }

    fun alternarPais(codigo: String) {
        val actual = _estado.value.filtro
        val paises = actual.paises.toMutableSet()
        if (!paises.add(codigo)) paises.remove(codigo)
        aplicarFiltro(actual.copy(paises = paises))
    }

    fun alternarTipo(tipo: TipoEvento) {
        val actual = _estado.value.filtro
        val tipos = actual.tipos.toMutableSet()
        if (!tipos.add(tipo)) tipos.remove(tipo)
        aplicarFiltro(actual.copy(tipos = tipos))
    }

    fun cambiarAlertaMinima(nivel: NivelAlerta) {
        aplicarFiltro(_estado.value.filtro.copy(alertaMinima = nivel))
    }

    fun buscar(texto: String) {
        aplicarFiltro(_estado.value.filtro.copy(texto = texto))
    }

    fun limpiarFiltros() {
        aplicarFiltro(Filtro())
    }

    class Factory(private val repositorio: RepositorioEventos) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T =
            EventosViewModel(repositorio) as T
    }
}
