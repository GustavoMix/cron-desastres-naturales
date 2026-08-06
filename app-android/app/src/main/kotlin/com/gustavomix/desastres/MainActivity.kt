package com.gustavomix.desastres

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import com.gustavomix.desastres.data.RepositorioEventos
import com.gustavomix.desastres.ui.EventosViewModel
import com.gustavomix.desastres.ui.PantallaEventos
import com.gustavomix.desastres.ui.TemaDesastres

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val repositorio = RepositorioEventos(RepositorioEventos.crearCliente(cacheDir))

        setContent {
            TemaDesastres {
                PantallaEventos(
                    viewModel = viewModel(factory = EventosViewModel.Factory(repositorio)),
                )
            }
        }
    }
}
